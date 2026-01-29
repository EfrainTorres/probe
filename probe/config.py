"""Configuration loading for Probe."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel

from probe.types import WorkspaceConfig


def get_repo_id(project_root: Path) -> str:
    """Get repo identifier from git remote origin URL, or directory name as fallback."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to directory name
    return project_root.name

# Environment variable defaults
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_TEI_URL = "http://127.0.0.1:8080"
DEFAULT_RERANKER_URL = "http://127.0.0.1:8083"


class ProbeConfig(BaseModel):
    """Runtime configuration from environment."""

    qdrant_url: str = DEFAULT_QDRANT_URL
    tei_url: str = DEFAULT_TEI_URL
    reranker_url: str | None = None
    preset: str = "lite"

    @classmethod
    def from_env(cls) -> ProbeConfig:
        """Load configuration from environment variables."""
        preset = os.getenv("PROBE_PRESET", "lite")
        reranker_url = os.getenv("RERANKER_URL")

        # balanced and pro presets enable reranker by default
        if reranker_url is None and preset in ("balanced", "pro"):
            reranker_url = DEFAULT_RERANKER_URL

        return cls(
            qdrant_url=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL),
            tei_url=os.getenv("TEI_EMBED_URL", DEFAULT_TEI_URL),
            reranker_url=reranker_url,
            preset=preset,
        )


def get_probe_dir(project_root: Path) -> Path:
    """Get the .probe directory for a project."""
    return project_root / ".probe"


def load_workspace_config(project_root: Path) -> WorkspaceConfig | None:
    """Load workspace config from .probe/config.json, or None if not initialized."""
    config_path = get_probe_dir(project_root) / "config.json"
    if not config_path.exists():
        return None

    data = json.loads(config_path.read_text())
    return WorkspaceConfig(**data)


def save_workspace_config(project_root: Path, config: WorkspaceConfig) -> None:
    """Save workspace config to .probe/config.json."""
    probe_dir = get_probe_dir(project_root)
    probe_dir.mkdir(parents=True, exist_ok=True)

    config_path = probe_dir / "config.json"
    config_path.write_text(config.model_dump_json(indent=2))


def init_workspace(project_root: Path, preset: str = "lite") -> WorkspaceConfig:
    """Initialize a new workspace with a fresh UUID."""
    config = WorkspaceConfig(
        workspace_id=uuid4(),
        repo_id=get_repo_id(project_root),
        preset=preset,
    )
    save_workspace_config(project_root, config)
    return config


def get_workspace_id(project_root: Path) -> UUID | None:
    """Get the workspace ID, or None if not initialized."""
    config = load_workspace_config(project_root)
    return config.workspace_id if config else None
