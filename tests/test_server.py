"""Tests for MCP server module."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.types import TextContent

from probe.server import handle_open_file


class TestOpenFile:
    """Tests for open_file tool."""

    @pytest.mark.asyncio
    async def test_open_file_valid(self, temp_project: Path, monkeypatch):
        # Change cwd to temp_project for sandbox validation
        monkeypatch.chdir(temp_project)

        result = await handle_open_file({
            "path": "main.py",
            "start_line": 1,
            "end_line": 5,
        })

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "def hello" in result[0].text or "Main module" in result[0].text

    @pytest.mark.asyncio
    async def test_open_file_not_found(self, temp_project: Path, monkeypatch):
        monkeypatch.chdir(temp_project)

        result = await handle_open_file({
            "path": "nonexistent.py",
            "start_line": 1,
            "end_line": 10,
        })

        assert len(result) == 1
        assert "not found" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_open_file_escape_attempt(self, temp_project: Path, monkeypatch):
        monkeypatch.chdir(temp_project)

        result = await handle_open_file({
            "path": "../../../etc/passwd",
            "start_line": 1,
            "end_line": 10,
        })

        assert len(result) == 1
        # Should either fail with escape error or not found
        text = result[0].text.lower()
        assert "escapes" in text or "not found" in text or "error" in text
