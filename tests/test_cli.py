"""Tests for CLI module."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from probe.cli import app

runner = CliRunner()


class TestCLI:
    """Tests for CLI commands."""

    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "probe" in result.stdout

    def test_init(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Initialized workspace" in result.stdout
        assert (tmp_path / ".probe" / "config.json").exists()

    def test_init_already_initialized(self, tmp_path: Path) -> None:
        # First init
        runner.invoke(app, ["init", str(tmp_path)])

        # Second init should fail
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 1
        assert "Already initialized" in result.stdout

    def test_serve_not_initialized(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["serve", str(tmp_path)])
        assert result.exit_code == 1
        # serve uses stderr since stdout is reserved for MCP protocol
        assert "Not initialized" in result.output

    def test_scan_not_initialized(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["scan", str(tmp_path)])
        assert result.exit_code == 1
        assert "Not initialized" in result.stdout
