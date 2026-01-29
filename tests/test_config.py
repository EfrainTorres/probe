"""Tests for config module."""

from __future__ import annotations

from pathlib import Path

from probe.config import (
    ProbeConfig,
    get_workspace_id,
    init_workspace,
    load_workspace_config,
)


class TestProbeConfig:
    """Tests for ProbeConfig."""

    def test_defaults(self):
        config = ProbeConfig()

        assert config.qdrant_url == "http://127.0.0.1:6333"
        assert config.tei_url == "http://127.0.0.1:8080"
        assert config.preset == "lite"
        assert config.reranker_url is None

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("QDRANT_URL", "http://custom:6333")
        monkeypatch.setenv("TEI_EMBED_URL", "http://custom:8080")
        monkeypatch.setenv("PROBE_PRESET", "balanced")

        config = ProbeConfig.from_env()

        assert config.qdrant_url == "http://custom:6333"
        assert config.tei_url == "http://custom:8080"
        assert config.preset == "balanced"
        # balanced preset enables reranker by default
        assert config.reranker_url == "http://127.0.0.1:8083"


class TestWorkspaceConfig:
    """Tests for workspace configuration."""

    def test_init_workspace(self, tmp_path: Path):
        config = init_workspace(tmp_path, preset="lite")

        assert config.workspace_id is not None
        assert config.preset == "lite"

        # Should create .probe directory
        assert (tmp_path / ".probe").is_dir()
        assert (tmp_path / ".probe" / "config.json").is_file()

    def test_load_workspace_config(self, tmp_path: Path):
        # Initialize first
        original = init_workspace(tmp_path)

        # Load it back
        loaded = load_workspace_config(tmp_path)

        assert loaded is not None
        assert loaded.workspace_id == original.workspace_id
        assert loaded.preset == original.preset

    def test_load_nonexistent(self, tmp_path: Path):
        config = load_workspace_config(tmp_path)
        assert config is None

    def test_get_workspace_id(self, tmp_path: Path):
        # Before init
        assert get_workspace_id(tmp_path) is None

        # After init
        config = init_workspace(tmp_path)
        assert get_workspace_id(tmp_path) == config.workspace_id

    def test_double_init_fails(self, tmp_path: Path):
        init_workspace(tmp_path)

        # Second init should detect existing config
        existing = load_workspace_config(tmp_path)
        assert existing is not None
