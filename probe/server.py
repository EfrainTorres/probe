"""MCP server with search, open_file, and index_status tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from probe.config import ProbeConfig, load_workspace_config
from probe.retrieval import search as retrieval_search
from probe.storage import QdrantClient
from probe.types import IndexStatus

if TYPE_CHECKING:
    from probe.watcher import WatcherState

# MCP server instance
server = Server("probe")

# Server configuration (set before running)
_project_root: Path | None = None
_watcher_state: WatcherState | None = None
_manifest_path: Path | None = None


def set_project_root(path: Path) -> None:
    """Set the project root for the server."""
    global _project_root, _manifest_path
    _project_root = path
    _manifest_path = path / ".probe" / "manifest.sqlite"


def get_project_root() -> Path:
    """Get the project root, falling back to cwd if not set."""
    return _project_root or Path.cwd()


def set_watcher_state(state: WatcherState) -> None:
    """Set the watcher state for index_status queries."""
    global _watcher_state
    _watcher_state = state


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="search",
            description="Semantic code search across the indexed codebase.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 12,
                        "description": "Number of results to return.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["fast", "quality", "auto"],
                        "default": "auto",
                        "description": "Search mode: fast, quality (rerank), or auto.",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Optional steering instruction for reranker.",
                    },
                    "filters": {
                        "type": "object",
                        "properties": {
                            "languages": {"type": "array", "items": {"type": "string"}},
                            "chunk_kinds": {"type": "array", "items": {"type": "string"}},
                            "include_globs": {"type": "array", "items": {"type": "string"}},
                            "exclude_globs": {"type": "array", "items": {"type": "string"}},
                        },
                        "description": "Optional pre-filters for search.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="open_file",
            description="Read exact lines from a file on disk.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repo-relative file path.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line (1-indexed).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line (1-indexed, inclusive).",
                    },
                },
                "required": ["path", "start_line", "end_line"],
            },
        ),
        Tool(
            name="index_status",
            description="Get indexing health and statistics.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    if name == "search":
        return await handle_search(arguments)
    elif name == "open_file":
        return await handle_open_file(arguments)
    elif name == "index_status":
        return await handle_index_status(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_search(args: dict[str, Any]) -> list[TextContent]:
    """Handle search tool call."""
    query = args.get("query", "")
    top_k = args.get("top_k", 12)
    mode = args.get("mode", "auto")
    instruction = args.get("instruction")
    filters = args.get("filters")

    project_root = get_project_root()

    # Load workspace config
    workspace_config = load_workspace_config(project_root)
    if not workspace_config:
        return [TextContent(
            type="text", text="Error: Workspace not initialized. Run 'probe init' first."
        )]

    # Load runtime config (respects workspace preset via env)
    config = ProbeConfig.from_env()

    # Create Qdrant client with workspace's preset
    qdrant = QdrantClient(url=config.qdrant_url, preset=workspace_config.preset)

    try:
        results = await retrieval_search(
            query=query,
            repo_id=workspace_config.repo_id,
            workspace_id=workspace_config.workspace_id,
            project_root=project_root,
            config=config,
            qdrant=qdrant,
            top_k=top_k,
            mode=mode,
            instruction=instruction,
            filters=filters,
        )

        # Format results for MCP response
        output = []
        for r in results:
            output.append({
                "path": str(r.path),
                "start_line": r.start_line,
                "end_line": r.end_line,
                "snippet": r.snippet,
                "score": r.score,
                "stale": r.stale,
                "source": r.source,
                "signals": r.signals,
            })

        return [TextContent(type="text", text=json.dumps(output, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: Search failed: {e}")]


async def handle_open_file(args: dict[str, Any]) -> list[TextContent]:
    """Handle open_file tool call with sandbox validation."""
    path_str = args.get("path", "")
    start_line = args.get("start_line", 1)
    end_line = args.get("end_line", 1)

    project_root = get_project_root()

    # Resolve path and validate sandbox
    requested = (project_root / path_str).resolve()

    # Security: reject symlinks that escape project root
    try:
        real_path = requested.resolve(strict=True)
        if not str(real_path).startswith(str(project_root)):
            return [TextContent(type="text", text=f"Error: Path escapes project root: {path_str}")]
    except FileNotFoundError:
        return [TextContent(type="text", text=f"Error: File not found: {path_str}")]

    # Read lines and get file metadata
    try:
        file_content = real_path.read_bytes()
        file_hash = hashlib.sha256(file_content).hexdigest()
        mtime = real_path.stat().st_mtime

        lines = file_content.decode("utf-8").splitlines()
        # Convert to 0-indexed, clamp to valid range
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        selected = lines[start_idx:end_idx]

        # Format with line numbers
        numbered = [f"{i + start_line}: {line}" for i, line in enumerate(selected)]
        content = "\n".join(numbered)

        # Return content with metadata per plan.md line 590
        result = {
            "content": content,
            "file_hash": file_hash,
            "mtime": mtime,
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except UnicodeDecodeError:
        return [TextContent(type="text", text=f"Error: File is not valid UTF-8: {path_str}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error reading file: {e}")]


async def handle_index_status(args: dict[str, Any]) -> list[TextContent]:
    """Handle index_status tool call."""
    project_root = get_project_root()
    workspace_config = load_workspace_config(project_root)

    # Get stats from manifest if available
    files_indexed = 0
    chunks_indexed = 0

    if _manifest_path and _manifest_path.exists():
        from probe.storage import Manifest

        manifest = Manifest(_manifest_path)
        try:
            await manifest.connect()
            stats = await manifest.get_stats()
            files_indexed = stats.get("files_indexed", 0)
            chunks_indexed = stats.get("chunks_indexed", 0)
        except Exception:
            pass
        finally:
            await manifest.close()

    # Get watcher state
    watcher_running = _watcher_state.running if _watcher_state else False
    index_generation = _watcher_state.index_generation if _watcher_state else 0
    last_scan = _watcher_state.last_scan_time if _watcher_state else 0

    # Convert monotonic time to datetime
    last_scan_time: datetime | None = None
    if last_scan > 0:
        # Approximate: monotonic offset from current time
        from time import monotonic

        offset = monotonic() - last_scan
        last_scan_time = datetime.now(UTC) - timedelta(seconds=offset)

    # Check backend connectivity
    config = ProbeConfig.from_env()
    backend_reachable = False
    dense_available = False
    bm25_available = False
    reranker_available = False

    try:
        import httpx

        # Check TEI
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{config.tei_url}/health", timeout=2.0)
                dense_available = resp.status_code == 200
            except Exception:
                pass

            # Check Qdrant (BM25 is always available with Qdrant >= 1.15.2)
            try:
                preset = workspace_config.preset if workspace_config else "lite"
                qdrant = QdrantClient(url=config.qdrant_url, preset=preset)
                bm25_available = await qdrant.health_check()
                backend_reachable = bm25_available
            except Exception:
                pass

            # Check reranker if configured
            if config.reranker_url:
                try:
                    resp = await client.get(f"{config.reranker_url}/health", timeout=2.0)
                    reranker_available = resp.status_code == 200
                except Exception:
                    pass
    except Exception:
        pass

    status = IndexStatus(
        watcher_running=watcher_running,
        last_scan_time=last_scan_time,
        files_indexed=files_indexed,
        chunks_indexed=chunks_indexed,
        index_generation=index_generation,
        backend_reachable=backend_reachable,
        current_preset=workspace_config.preset if workspace_config else "lite",
        dense_available=dense_available,
        bm25_available=bm25_available,
        reranker_available=reranker_available,
    )

    return [TextContent(type="text", text=status.model_dump_json(indent=2))]


async def run_server(project_root: Path | None = None) -> None:
    """Run the MCP server over stdio."""
    if project_root:
        set_project_root(project_root)

    # Log to stderr (stdout is reserved for MCP protocol)
    print(f"Probe MCP server starting for: {get_project_root()}", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(project_root: Path | None = None) -> None:
    """Entry point for running the server."""
    asyncio.run(run_server(project_root))


if __name__ == "__main__":
    main()
