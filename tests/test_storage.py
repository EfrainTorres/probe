"""Tests for storage module."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from probe.storage.manifest import Manifest
from probe.types import ChunkKind, IndexedChunk


@pytest.fixture
async def manifest(tmp_path: Path):
    """Create a manifest for testing."""
    db_path = tmp_path / "manifest.sqlite"
    m = Manifest(db_path)
    await m.connect()
    yield m
    await m.close()


class TestManifest:
    """Tests for SQLite manifest."""

    @pytest.mark.asyncio
    async def test_file_operations(self, manifest: Manifest):
        file_path = Path("test.py")

        # Initially not found
        assert await manifest.get_file(file_path) is None

        # Insert
        await manifest.upsert_file(
            file_path=file_path,
            mtime=1234567890.0,
            size=1000,
            file_hash="abc123",
        )

        # Now found
        data = await manifest.get_file(file_path)
        assert data is not None
        assert data["mtime"] == 1234567890.0
        assert data["size"] == 1000
        assert data["file_hash"] == "abc123"

        # Update
        await manifest.upsert_file(
            file_path=file_path,
            mtime=1234567900.0,
            size=2000,
            file_hash="def456",
        )

        data = await manifest.get_file(file_path)
        assert data["mtime"] == 1234567900.0
        assert data["size"] == 2000

        # Delete
        await manifest.delete_file(file_path)
        assert await manifest.get_file(file_path) is None

    @pytest.mark.asyncio
    async def test_chunk_operations(self, manifest: Manifest):
        file_path = Path("test.py")

        # First add the file
        await manifest.upsert_file(
            file_path=file_path,
            mtime=1234567890.0,
            size=1000,
            file_hash="abc123",
        )

        # Add chunks
        chunks = [
            IndexedChunk(
                point_id=uuid4(),
                file_path=file_path,
                start_line=1,
                end_line=10,
                chunk_hash="hash1",
                chunk_idx=0,
                kind=ChunkKind.CODE,
            ),
            IndexedChunk(
                point_id=uuid4(),
                file_path=file_path,
                start_line=11,
                end_line=20,
                chunk_hash="hash2",
                chunk_idx=1,
                kind=ChunkKind.CODE,
            ),
        ]
        await manifest.upsert_chunks(chunks)

        # Get by position
        chunk = await manifest.get_chunk_by_position(file_path, 1, 10)
        assert chunk is not None
        assert chunk["chunk_hash"] == "hash1"
        assert chunk["chunk_idx"] == 0

        # Get neighbors
        neighbors = await manifest.get_neighbor_chunks(file_path, 1)
        assert len(neighbors) == 1  # Only chunk_idx=0 exists as neighbor

    @pytest.mark.asyncio
    async def test_stats(self, manifest: Manifest):
        # Empty initially
        stats = await manifest.get_stats()
        assert stats["files_indexed"] == 0
        assert stats["chunks_indexed"] == 0

        # Add a file
        await manifest.upsert_file(
            file_path=Path("test.py"),
            mtime=1234567890.0,
            size=1000,
            file_hash="abc123",
        )

        stats = await manifest.get_stats()
        assert stats["files_indexed"] == 1

    @pytest.mark.asyncio
    async def test_workspace_meta(self, manifest: Manifest):
        # Not found initially
        assert await manifest.get_workspace_meta("foo") is None

        # Set and get
        await manifest.set_workspace_meta("foo", "bar")
        assert await manifest.get_workspace_meta("foo") == "bar"

        # Update
        await manifest.set_workspace_meta("foo", "baz")
        assert await manifest.get_workspace_meta("foo") == "baz"
