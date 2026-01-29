"""Shared Pydantic models for Probe."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChunkKind(str, Enum):
    """Type of content chunk."""

    CODE = "code"
    DOC = "doc"
    CONFIG = "config"


class Chunk(BaseModel):
    """A semantic chunk of a file."""

    file_path: Path
    start_line: int
    end_line: int
    content: str
    language: str | None = None
    kind: ChunkKind = ChunkKind.CODE
    symbol: str | None = None  # function/class name if applicable


class IndexedChunk(BaseModel):
    """A chunk stored in the index with metadata."""

    point_id: UUID
    file_path: Path
    start_line: int
    end_line: int
    chunk_hash: str  # sha256 truncated to 16 chars
    chunk_idx: int  # 0-based index within file
    language: str | None = None
    kind: ChunkKind = ChunkKind.CODE
    symbol: str | None = None


class SearchResult(BaseModel):
    """A single search result."""

    repo_id: str
    workspace_id: UUID
    path: Path
    start_line: int
    end_line: int
    snippet: str
    score: float
    stale: bool = False
    source: str  # "path#Lstart-Lend"
    signals: dict[str, Any] = Field(default_factory=dict)


class IndexStatus(BaseModel):
    """Status of the index for a workspace."""

    watcher_running: bool
    last_scan_time: datetime | None
    files_indexed: int
    chunks_indexed: int
    index_generation: int
    backend_reachable: bool
    last_error: str | None = None
    current_preset: str
    # Capability flags
    dense_available: bool
    bm25_available: bool
    reranker_available: bool
    # Progress (when indexing)
    indexing_in_progress: bool = False
    progress: dict[str, Any] | None = None


class WorkspaceConfig(BaseModel):
    """Configuration stored in .probe/config.json."""

    workspace_id: UUID
    repo_id: str
    preset: str = "lite"
    created_at: datetime = Field(default_factory=datetime.now)
