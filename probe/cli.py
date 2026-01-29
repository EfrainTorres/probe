"""CLI commands for Probe."""

from __future__ import annotations

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
    import sys

    from probe.server import main as run_mcp_server

    project_root = path.resolve()

    config = load_workspace_config(project_root)
    if not config:
        # Use stderr since stdout is for MCP protocol
        print("Error: Not initialized. Run 'probe init' first.", file=sys.stderr)
        raise typer.Exit(1)

    # Log to stderr (stdout reserved for MCP protocol)
    print(f"Workspace: {config.workspace_id}", file=sys.stderr)
    if watch:
        # TODO: Start watcher in background
        print("Watch mode: enabled (watcher not yet implemented)", file=sys.stderr)

    # Run the MCP server (blocks, handles stdin/stdout)
    run_mcp_server(project_root)


@app.command()
def scan(
    path: Path = typer.Argument(Path("."), help="Project root directory."),
) -> None:
    """Manually trigger a full index scan."""
    project_root = path.resolve()

    config = load_workspace_config(project_root)
    if not config:
        console.print("[red]Not initialized. Run 'probe init' first.[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Scanning {project_root}[/blue]")

    # TODO: Run indexer
    console.print("[yellow]Indexer not yet implemented[/yellow]")


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
