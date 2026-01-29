"""CLI commands for Probe."""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer
from rich.console import Console

from probe import __version__
from probe.config import init_workspace, load_workspace_config

app = typer.Typer(
    name="probe",
    help="RAG memory for agentic coders via MCP.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"probe {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Probe - RAG memory for agentic coders."""
    pass


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project root directory."),
    preset: str = typer.Option("lite", "--preset", "-p", help="Preset: lite, balanced, pro"),
) -> None:
    """Initialize Probe for a project."""
    project_root = path.resolve()

    existing = load_workspace_config(project_root)
    if existing:
        console.print(f"[yellow]Already initialized: {existing.workspace_id}[/yellow]")
        raise typer.Exit(1)

    config = init_workspace(project_root, preset=preset)
    console.print(f"[green]Initialized workspace: {config.workspace_id}[/green]")
    console.print(f"Preset: {config.preset}")
    console.print(f"Config: {project_root / '.probe' / 'config.json'}")


@app.command()
def serve(
    path: Path = typer.Argument(Path("."), help="Project root directory."),
    watch: bool = typer.Option(True, "--watch/--no-watch", help="Watch for file changes."),
) -> None:
    """Start the MCP server (and optionally watch for changes)."""
    import asyncio
    import sys

    from probe.config import ProbeConfig
    from probe.server import run_server, set_project_root, set_watcher_state
    from probe.storage import Manifest, QdrantClient

    project_root = path.resolve()

    workspace_config = load_workspace_config(project_root)
    if not workspace_config:
        # Use stderr since stdout is for MCP protocol
        print("Error: Not initialized. Run 'probe init' first.", file=sys.stderr)
        raise typer.Exit(1)

    # Log to stderr (stdout reserved for MCP protocol)
    print(f"Workspace: {workspace_config.workspace_id}", file=sys.stderr)
    print(f"Preset: {workspace_config.preset}", file=sys.stderr)

    async def run_with_watcher() -> None:
        # Set up project root
        set_project_root(project_root)

        # Load runtime config
        config = ProbeConfig.from_env()

        # Initialize storage clients for watcher
        qdrant = QdrantClient(url=config.qdrant_url, preset=workspace_config.preset)
        await qdrant.ensure_collection()

        manifest = Manifest(project_root / ".probe" / "manifest.sqlite")
        await manifest.connect()

        watcher_task = None

        try:
            if watch:
                from probe.watcher import WatcherState, run_watcher

                # Create shared watcher state
                state = WatcherState()
                set_watcher_state(state)

                # Start watcher as background task
                watcher_task = asyncio.create_task(
                    run_watcher(
                        project_root=project_root,
                        repo_id=workspace_config.repo_id,
                        workspace_id=workspace_config.workspace_id,
                        config=config,
                        qdrant=qdrant,
                        manifest=manifest,
                        state=state,
                    )
                )
                print("Watch mode: enabled", file=sys.stderr)

            # Run MCP server (blocks until stdin closes)
            await run_server(project_root)

        finally:
            # Clean up
            if watcher_task:
                watcher_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher_task
            await manifest.close()

    asyncio.run(run_with_watcher())


@app.command()
def scan(
    path: Path = typer.Argument(Path("."), help="Project root directory."),
) -> None:
    """Manually trigger a full index scan."""
    import asyncio

    from probe.config import ProbeConfig
    from probe.indexing import run_scan
    from probe.storage import Manifest, QdrantClient

    project_root = path.resolve()

    workspace_config = load_workspace_config(project_root)
    if not workspace_config:
        console.print("[red]Not initialized. Run 'probe init' first.[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Scanning {project_root}[/blue]")
    console.print(f"Workspace: {workspace_config.workspace_id}")
    console.print(f"Preset: {workspace_config.preset}")

    # Load runtime config
    config = ProbeConfig.from_env()

    async def do_scan() -> dict[str, int]:
        # Initialize storage clients
        qdrant = QdrantClient(url=config.qdrant_url, preset=workspace_config.preset)
        await qdrant.ensure_collection()

        manifest = Manifest(project_root / ".probe" / "manifest.sqlite")
        await manifest.connect()

        try:
            stats = await run_scan(
                project_root=project_root,
                repo_id=workspace_config.repo_id,
                workspace_id=workspace_config.workspace_id,
                config=config,
                qdrant=qdrant,
                manifest=manifest,
            )
            return stats
        finally:
            await manifest.close()

    try:
        with console.status("[bold green]Indexing..."):
            stats = asyncio.run(do_scan())

        console.print("[green]Scan complete![/green]")
        console.print(f"  Files scanned: {stats['files_scanned']}")
        console.print(f"  Chunks indexed: {stats['chunks_indexed']}")

    except Exception as e:
        console.print(f"[red]Scan failed: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def prune(
    older_than: str = typer.Option("30d", "--older-than", help="Remove workspaces older than."),
) -> None:
    """Remove stale workspace data from Qdrant."""
    console.print(f"[blue]Pruning workspaces older than {older_than}[/blue]")

    # TODO: Prune stale workspaces
    console.print("[yellow]Prune not yet implemented[/yellow]")


@app.command()
def doctor() -> None:
    """Check system health: Qdrant, TEI, reranker connectivity."""
    console.print("[blue]Running health checks...[/blue]")

    # TODO: Health checks
    console.print("[yellow]Doctor not yet implemented[/yellow]")


if __name__ == "__main__":
    app()
