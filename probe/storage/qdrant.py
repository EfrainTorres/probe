"""Qdrant vector storage client."""

from __future__ import annotations

import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient as QdrantClientBase
from qdrant_client import models

from probe.types import Chunk

# Preset configurations
PRESET_CONFIG = {
    "lite": {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "dimensions": 1024,
    },
    "balanced": {
        "model": "Qwen/Qwen3-Embedding-4B",
        "dimensions": 2560,
    },
    "pro": {
        "model": "Qwen/Qwen3-Embedding-8B",
        "dimensions": 4096,
    },
}


class QdrantClient:
    """Wrapper around Qdrant client for Probe operations."""

    def __init__(self, url: str, preset: str = "lite"):
        self.client = QdrantClientBase(url=url)
        self.preset = preset
        self.config = PRESET_CONFIG[preset]
        self.collection_name = f"chunks_{preset}"

    async def ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=self.config["dimensions"],
                        distance=models.Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    "sparse_bm25": models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    ),
                },
            )

            # Create payload indexes for filtering
            for field in ["repo_id", "workspace_id", "file_path", "language", "chunk_kind"]:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )

    async def upsert_chunk(
        self,
        point_id: UUID,
        repo_id: str,
        workspace_id: UUID,
        file_path: Path,
        file_hash: str,
        chunk: Chunk,
        chunk_hash: str,
        dense_vector: list[float],
    ) -> None:
        """Upsert a chunk with dense and sparse vectors."""
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=str(point_id),
                    vector={
                        "dense": dense_vector,
                        "sparse_bm25": models.Document(
                            text=chunk.content,
                            model="qdrant/bm25",
                            options=models.Bm25Config(
                                language="none",  # No stemming for code
                                avg_len=150,
                            ),
                        ),
                    },
                    payload={
                        "repo_id": repo_id,
                        "workspace_id": str(workspace_id),
                        "file_path": str(file_path),
                        "file_hash": file_hash,
                        "chunk_hash": chunk_hash,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "language": chunk.language,
                        "chunk_kind": chunk.kind.value,
                        "symbol": chunk.symbol,
                        "indexed_at": datetime.now().isoformat(),
                    },
                ),
            ],
        )

    async def delete_by_file(self, workspace_id: UUID, file_path: Path) -> None:
        """Delete all chunks for a file."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="workspace_id",
                            match=models.MatchValue(value=str(workspace_id)),
                        ),
                        models.FieldCondition(
                            key="file_path",
                            match=models.MatchValue(value=str(file_path)),
                        ),
                    ],
                ),
            ),
        )

    async def delete_workspace(self, workspace_id: UUID) -> None:
        """Delete all chunks for a workspace."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="workspace_id",
                            match=models.MatchValue(value=str(workspace_id)),
                        ),
                    ],
                ),
            ),
        )

    async def hybrid_search(
        self,
        workspace_id: UUID,
        query_vector: list[float],
        query_text: str,
        limit: int = 30,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run hybrid dense + sparse search with RRF fusion."""
        # Build filter conditions
        must_conditions = [
            models.FieldCondition(
                key="workspace_id",
                match=models.MatchValue(value=str(workspace_id)),
            ),
        ]

        if filters:
            if "languages" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="language",
                        match=models.MatchAny(any=filters["languages"]),
                    )
                )
            if "chunk_kinds" in filters:
                must_conditions.append(
                    models.FieldCondition(
                        key="chunk_kind",
                        match=models.MatchAny(any=filters["chunk_kinds"]),
                    )
                )

        search_filter = models.Filter(must=must_conditions)

        # Hybrid search with RRF fusion
        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=query_vector,
                    using="dense",
                    limit=50,
                    filter=search_filter,
                ),
                models.Prefetch(
                    query=models.Document(
                        text=query_text,
                        model="qdrant/bm25",
                        options=models.Bm25Config(
                            language="none",
                            avg_len=150,
                        ),
                    ),
                    using="sparse_bm25",
                    limit=50,
                    filter=search_filter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )

        # Convert to dicts
        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                {
                    "point_id": point.id,
                    "score": point.score,
                    "repo_id": payload.get("repo_id"),
                    "workspace_id": payload.get("workspace_id"),
                    "file_path": payload.get("file_path"),
                    "chunk_hash": payload.get("chunk_hash"),
                    "start_line": payload.get("start_line"),
                    "end_line": payload.get("end_line"),
                    "language": payload.get("language"),
                    "symbol": payload.get("symbol"),
                    "signals": {
                        "dense_rank": None,  # TODO: Track individual ranks
                        "bm25_rank": None,
                    },
                }
            )

        # Apply glob filters (post-filter since Qdrant doesn't support glob matching)
        if filters:
            results = self._apply_glob_filters(results, filters)

        return results

    def _apply_glob_filters(
        self,
        results: list[dict[str, Any]],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply include_globs and exclude_globs filters to results."""
        include_globs = filters.get("include_globs")
        exclude_globs = filters.get("exclude_globs")

        if not include_globs and not exclude_globs:
            return results

        filtered = []
        for result in results:
            file_path = result.get("file_path", "")

            # Check include_globs: path must match at least one pattern
            if include_globs and not any(
                fnmatch.fnmatch(file_path, pattern) for pattern in include_globs
            ):
                continue

            # Check exclude_globs: path must not match any pattern
            if exclude_globs and any(
                fnmatch.fnmatch(file_path, pattern) for pattern in exclude_globs
            ):
                continue

            filtered.append(result)

        return filtered

    async def health_check(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
