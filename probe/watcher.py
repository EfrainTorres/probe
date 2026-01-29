"""File watcher for incremental indexing."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

from watchfiles import Change, awatch

from probe.config import ProbeConfig
from probe.indexing import index_file, run_scan
from probe.storage import Manifest, QdrantClient


@dataclass
class WatcherState:
    """Mutable state for the watcher."""

    running: bool = False
    last_scan_time: float = 0.0
    index_generation: int = 0
    pending_paths: set[Path] = field(default_factory=set)
    last_change_time: float = 0.0
    burst_count: int = 0
    burst_start_time: float = 0.0


# Configuration constants per plan.md section 7
DEBOUNCE_SECONDS = 3.0  # Trailing debounce
MAX_WAIT_SECONDS = 30.0  # Max wait before forced flush
STABLE_CHECK_SECONDS = 0.3  # File stability check
BURST_THRESHOLD = 50  # Events triggering full scan
BURST_WINDOW_SECONDS = 5.0  # Window for burst detection
RESCAN_INTERVAL_SECONDS = 15 * 60  # 15 minute periodic rescan


def _should_ignore(path: Path, project_root: Path) -> bool:
    """Check if path should be ignored."""
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        return True  # Outside project root

    parts = relative.parts

    # Ignore patterns
    ignore_dirs = {
        ".git",
        ".probe",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".eggs",
    }

    # Skip if in ignored directory (except .git/HEAD for branch detection)
    for part in parts[:-1]:
        if part in ignore_dirs or part.startswith("."):
            # Allow .git/HEAD specifically for branch detection
            return parts != (".git", "HEAD")

    # Skip binary files
    return path.suffix in {".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".pyc"}


def _is_branch_switch(path: Path, project_root: Path) -> bool:
    """Check if change is a branch switch (.git/HEAD change)."""
    try:
        relative = path.relative_to(project_root)
        return relative.parts == (".git", "HEAD")
    except ValueError:
        return False


async def _wait_for_stable(path: Path, timeout: float = STABLE_CHECK_SECONDS) -> bool:
    """Wait for file to stabilize (mtime stops changing)."""
    if not path.exists():
        return True  # Deleted files are "stable"

    try:
        initial_stat = path.stat()
        await asyncio.sleep(timeout)

        if not path.exists():
            return True

        final_stat = path.stat()
        return (
            initial_stat.st_mtime == final_stat.st_mtime
            and initial_stat.st_size == final_stat.st_size
        )
    except OSError:
        return True  # File inaccessible, treat as stable


async def process_changes(
    paths: set[Path],
    project_root: Path,
    repo_id: str,
    workspace_id: UUID,
    config: ProbeConfig,
    qdrant: QdrantClient,
    manifest: Manifest,
) -> int:
    """Process a batch of changed files. Returns chunks indexed."""
    total_chunks = 0

    for path in paths:
        if not path.exists():
            # File was deleted - handled by manifest cleanup on next scan
            continue

        if not await _wait_for_stable(path):
            # File still changing, will catch on next batch
            continue

        try:
            chunks = await index_file(
                file_path=path,
                project_root=project_root,
                repo_id=repo_id,
                workspace_id=workspace_id,
                config=config,
                qdrant=qdrant,
                manifest=manifest,
            )
            total_chunks += chunks
        except Exception as e:
            print(f"Watcher: Error indexing {path}: {e}", file=sys.stderr)

    return total_chunks


async def run_watcher(
    project_root: Path,
    repo_id: str,
    workspace_id: UUID,
    config: ProbeConfig,
    qdrant: QdrantClient,
    manifest: Manifest,
    state: WatcherState,
    on_scan_complete: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> None:
    """Run the file watcher with debouncing and burst protection.

    Args:
        project_root: Root directory to watch
        repo_id: Repository identifier
        workspace_id: Workspace UUID
        config: Runtime configuration
        qdrant: Qdrant client
        manifest: SQLite manifest
        state: Shared watcher state
        on_scan_complete: Optional callback after scan completes
    """
    state.running = True
    state.last_scan_time = monotonic()
    print(f"Watcher: Started watching {project_root}", file=sys.stderr)

    # Background task for periodic rescan
    async def periodic_rescan() -> None:
        while state.running:
            await asyncio.sleep(RESCAN_INTERVAL_SECONDS)
            if not state.running:
                break

            elapsed = monotonic() - state.last_scan_time
            if elapsed >= RESCAN_INTERVAL_SECONDS:
                print("Watcher: Periodic rescan triggered", file=sys.stderr)
                try:
                    stats = await run_scan(
                        project_root=project_root,
                        repo_id=repo_id,
                        workspace_id=workspace_id,
                        config=config,
                        qdrant=qdrant,
                        manifest=manifest,
                    )
                    state.last_scan_time = monotonic()
                    state.index_generation += 1
                    print(
                        f"Watcher: Periodic scan complete - {stats['chunks_indexed']} chunks",
                        file=sys.stderr,
                    )
                    if on_scan_complete:
                        await on_scan_complete()
                except Exception as e:
                    print(f"Watcher: Periodic scan failed: {e}", file=sys.stderr)

    # Start periodic rescan task
    rescan_task = asyncio.create_task(periodic_rescan())

    # Debounce flush task
    flush_task: asyncio.Task[None] | None = None

    async def flush_pending() -> None:
        """Flush pending changes after debounce period."""
        nonlocal flush_task

        await asyncio.sleep(DEBOUNCE_SECONDS)

        if not state.pending_paths:
            return

        paths_to_process = state.pending_paths.copy()
        state.pending_paths.clear()

        print(f"Watcher: Processing {len(paths_to_process)} changed files", file=sys.stderr)

        chunks = await process_changes(
            paths=paths_to_process,
            project_root=project_root,
            repo_id=repo_id,
            workspace_id=workspace_id,
            config=config,
            qdrant=qdrant,
            manifest=manifest,
        )

        if chunks > 0:
            state.index_generation += 1
            state.last_scan_time = monotonic()
            print(f"Watcher: Indexed {chunks} chunks", file=sys.stderr)
            if on_scan_complete:
                await on_scan_complete()

        flush_task = None

    try:
        async for changes in awatch(project_root, recursive=True):
            if not state.running:
                break

            now = monotonic()
            files_changed: set[Path] = set()
            branch_switched = False

            for change_type, path_str in changes:
                path = Path(path_str)

                # Check for branch switch
                if _is_branch_switch(path, project_root):
                    branch_switched = True
                    continue

                # Skip ignored paths
                if _should_ignore(path, project_root):
                    continue

                # Only process file modifications and creations
                if change_type in (Change.modified, Change.added):
                    files_changed.add(path)

            # Handle branch switch - trigger full scan
            if branch_switched:
                print("Watcher: Branch switch detected, scheduling full scan", file=sys.stderr)
                state.pending_paths.clear()
                if flush_task:
                    flush_task.cancel()
                    flush_task = None

                try:
                    stats = await run_scan(
                        project_root=project_root,
                        repo_id=repo_id,
                        workspace_id=workspace_id,
                        config=config,
                        qdrant=qdrant,
                        manifest=manifest,
                    )
                    state.last_scan_time = monotonic()
                    state.index_generation += 1
                    print(
                        f"Watcher: Branch scan complete - {stats['chunks_indexed']} chunks",
                        file=sys.stderr,
                    )
                    if on_scan_complete:
                        await on_scan_complete()
                except Exception as e:
                    print(f"Watcher: Branch scan failed: {e}", file=sys.stderr)
                continue

            if not files_changed:
                continue

            # Burst detection
            if now - state.burst_start_time > BURST_WINDOW_SECONDS:
                state.burst_count = 0
                state.burst_start_time = now

            state.burst_count += len(files_changed)

            if state.burst_count > BURST_THRESHOLD:
                # Too many changes - trigger full scan instead
                print(
                    f"Watcher: Burst detected ({state.burst_count} events), scheduling full scan",
                    file=sys.stderr,
                )
                state.pending_paths.clear()
                state.burst_count = 0

                if flush_task:
                    flush_task.cancel()
                    flush_task = None

                try:
                    stats = await run_scan(
                        project_root=project_root,
                        repo_id=repo_id,
                        workspace_id=workspace_id,
                        config=config,
                        qdrant=qdrant,
                        manifest=manifest,
                    )
                    state.last_scan_time = monotonic()
                    state.index_generation += 1
                    print(
                        f"Watcher: Burst scan complete - {stats['chunks_indexed']} chunks",
                        file=sys.stderr,
                    )
                    if on_scan_complete:
                        await on_scan_complete()
                except Exception as e:
                    print(f"Watcher: Burst scan failed: {e}", file=sys.stderr)
                continue

            # Add to pending and reset debounce
            state.pending_paths.update(files_changed)
            state.last_change_time = now

            # Check max wait
            first_change_time = now - len(state.pending_paths) * 0.01  # Approximate
            if flush_task and (now - first_change_time) > MAX_WAIT_SECONDS:
                # Force flush due to max wait
                flush_task.cancel()
                flush_task = None
                await flush_pending()
            elif not flush_task:
                # Start new debounce timer
                flush_task = asyncio.create_task(flush_pending())

    except asyncio.CancelledError:
        pass
    finally:
        state.running = False
        rescan_task.cancel()
        if flush_task:
            flush_task.cancel()
        print("Watcher: Stopped", file=sys.stderr)
