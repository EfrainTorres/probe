"""SQLite manifest for tracking indexed files and chunks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from probe.types import IndexedChunk


class Manifest:
    """SQLite-based manifest for tracking file and chunk state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and ensure schema exists."""
        self._conn = await aiosqlite.connect(self.db_path)
        await self._ensure_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        assert self._conn is not None

        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                file_hash TEXT NOT NULL,
                last_indexed_at REAL NOT NULL DEFAULT (unixepoch()),
                last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                chunk_hash TEXT NOT NULL,
                point_id TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL,
                PRIMARY KEY (file_path, start_line, end_line),
                FOREIGN KEY (file_path) REFERENCES files(file_path) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS workspace (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path);
            CREATE INDEX IF NOT EXISTS idx_chunks_point ON chunks(point_id);
            """
        )
        await self._conn.commit()

    async def get_file(self, file_path: Path) -> dict[str, Any] | None:
        """Get file metadata, or None if not indexed."""
        assert self._conn is not None

        query = """
            SELECT mtime, size, file_hash, last_indexed_at, last_error
            FROM files WHERE file_path = ?
        """
        async with self._conn.execute(query, (str(file_path),)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "mtime": row[0],
                    "size": row[1],
                    "file_hash": row[2],
                    "last_indexed_at": row[3],
                    "last_error": row[4],
                }
            return None

    async def upsert_file(
        self,
        file_path: Path,
        mtime: float,
        size: int,
        file_hash: str,
        error: str | None = None,
    ) -> None:
        """Insert or update file metadata."""
        assert self._conn is not None

        await self._conn.execute(
            """
            INSERT INTO files (file_path, mtime, size, file_hash, last_error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                mtime = excluded.mtime,
                size = excluded.size,
                file_hash = excluded.file_hash,
                last_indexed_at = unixepoch(),
                last_error = excluded.last_error
            """,
            (str(file_path), mtime, size, file_hash, error),
        )
        await self._conn.commit()

    async def delete_file(self, file_path: Path) -> None:
        """Delete file and its chunks from manifest."""
        assert self._conn is not None

        await self._conn.execute(
            "DELETE FROM files WHERE file_path = ?",
            (str(file_path),),
        )
        await self._conn.commit()

    async def delete_file_chunks(self, file_path: Path) -> None:
        """Delete all chunks for a file."""
        assert self._conn is not None

        await self._conn.execute(
            "DELETE FROM chunks WHERE file_path = ?",
            (str(file_path),),
        )
        await self._conn.commit()

    async def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """Insert or update multiple chunks."""
        assert self._conn is not None

        await self._conn.executemany(
            """
            INSERT INTO chunks (file_path, start_line, end_line, chunk_hash, point_id, chunk_idx)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path, start_line, end_line) DO UPDATE SET
                chunk_hash = excluded.chunk_hash,
                point_id = excluded.point_id,
                chunk_idx = excluded.chunk_idx
            """,
            [
                (
                    str(c.file_path),
                    c.start_line,
                    c.end_line,
                    c.chunk_hash,
                    str(c.point_id),
                    c.chunk_idx,
                )
                for c in chunks
            ],
        )
        await self._conn.commit()

    async def get_chunk_by_position(
        self, file_path: Path, start_line: int, end_line: int
    ) -> dict[str, Any] | None:
        """Get chunk by position."""
        assert self._conn is not None

        query = """
            SELECT chunk_hash, point_id, chunk_idx FROM chunks
            WHERE file_path = ? AND start_line = ? AND end_line = ?
        """
        async with self._conn.execute(
            query, (str(file_path), start_line, end_line)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "chunk_hash": row[0],
                    "point_id": row[1],
                    "chunk_idx": row[2],
                }
            return None

    async def get_neighbor_chunks(
        self, file_path: Path, chunk_idx: int
    ) -> list[dict[str, Any]]:
        """Get adjacent chunks (prev and next) for context expansion."""
        assert self._conn is not None

        neighbors = []
        async with self._conn.execute(
            """
            SELECT start_line, end_line, chunk_hash, point_id, chunk_idx
            FROM chunks
            WHERE file_path = ? AND chunk_idx IN (?, ?)
            ORDER BY chunk_idx
            """,
            (str(file_path), chunk_idx - 1, chunk_idx + 1),
        ) as cursor:
            async for row in cursor:
                neighbors.append(
                    {
                        "start_line": row[0],
                        "end_line": row[1],
                        "chunk_hash": row[2],
                        "point_id": row[3],
                        "chunk_idx": row[4],
                    }
                )

        return neighbors

    async def get_stats(self) -> dict[str, int]:
        """Get index statistics."""
        assert self._conn is not None

        files_count = 0
        chunks_count = 0

        async with self._conn.execute("SELECT COUNT(*) FROM files") as cursor:
            row = await cursor.fetchone()
            if row:
                files_count = row[0]

        async with self._conn.execute("SELECT COUNT(*) FROM chunks") as cursor:
            row = await cursor.fetchone()
            if row:
                chunks_count = row[0]

        return {
            "files_indexed": files_count,
            "chunks_indexed": chunks_count,
        }

    async def set_workspace_meta(self, key: str, value: str) -> None:
        """Set workspace metadata."""
        assert self._conn is not None

        await self._conn.execute(
            "INSERT OR REPLACE INTO workspace (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._conn.commit()

    async def get_workspace_meta(self, key: str) -> str | None:
        """Get workspace metadata."""
        assert self._conn is not None

        async with self._conn.execute(
            "SELECT value FROM workspace WHERE key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
