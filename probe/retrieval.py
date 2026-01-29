"""Retrieval pipeline: dense -> sparse -> fusion -> rerank."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from probe.config import ProbeConfig
from probe.storage import QdrantClient
from probe.types import SearchResult

# Instruction template for code search (per Qwen3-Embedding docs)
QUERY_INSTRUCTION = (
    "Instruct: Given a code search query, retrieve relevant code snippets\n"
    "Query: "
)


async def embed_query(query: str, config: ProbeConfig) -> list[float]:
    """Embed a search query using TEI with instruction prefix."""
    # Qwen3-Embedding recommends instruction-style queries for 1-5% better retrieval
    formatted_query = f"{QUERY_INSTRUCTION}{query}"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config.tei_url}/embed",
            json={
                "inputs": [formatted_query],
                "truncate": True,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        embeddings = response.json()
        return embeddings[0]


async def rerank(
    query: str,
    documents: list[str],
    instruction: str | None,
    config: ProbeConfig,
) -> list[tuple[int, float]]:
    """Rerank documents using the reranker service."""
    if not config.reranker_url:
        # No reranker configured, return original order
        return [(i, 1.0 - i * 0.01) for i in range(len(documents))]

    async with httpx.AsyncClient() as client:
        payload: dict[str, Any] = {
            "query": query,
            "documents": documents,
        }
        if instruction:
            payload["instruction"] = instruction

        response = await client.post(
            f"{config.reranker_url}/rerank",
            json=payload,
            timeout=5.0,  # 300ms target, 5s max
        )
        response.raise_for_status()
        results = response.json()

        # Expected format: [{"index": 0, "score": 0.95}, ...]
        return [(r["index"], r["score"]) for r in results]


def generate_snippet(
    file_path: Path,
    start_line: int,
    end_line: int,
    project_root: Path,
    chunk_hash: str | None = None,
    max_lines: int = 15,
) -> tuple[str, bool]:
    """Generate snippet from disk, returning (snippet, stale).

    Args:
        file_path: Repo-relative path to the file
        start_line: 1-indexed start line
        end_line: 1-indexed end line (inclusive)
        project_root: Absolute path to project root
        chunk_hash: Expected hash (truncated sha256) for staleness check
        max_lines: Maximum lines to include in snippet
    """
    full_path = project_root / file_path

    try:
        lines = full_path.read_text().splitlines()
    except (FileNotFoundError, UnicodeDecodeError):
        return "(file not found or unreadable)", True

    # Clamp to valid range
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)
    selected = lines[start_idx:end_idx]

    # Check staleness by comparing chunk hash
    stale = False
    if chunk_hash:
        content = "\n".join(selected)
        current_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        stale = current_hash != chunk_hash

    # Truncate for snippet display
    if len(selected) > max_lines:
        selected = selected[:max_lines]
        selected.append("...")

    snippet = "\n".join(selected)
    return snippet, stale


async def search(
    query: str,
    repo_id: str,
    workspace_id: UUID,
    project_root: Path,
    config: ProbeConfig,
    qdrant: QdrantClient,
    top_k: int = 12,
    mode: str = "auto",
    instruction: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """Run hybrid search with optional reranking."""
    # Determine effective mode
    effective_mode = mode
    if mode == "auto":
        effective_mode = "quality" if config.reranker_url else "fast"

    # Step 1: Embed query
    query_vector = await embed_query(query, config)

    # Step 2: Hybrid search (dense + BM25 with RRF fusion)
    # Request more candidates if reranking
    fusion_limit = 30 if effective_mode == "quality" else top_k

    candidates = await qdrant.hybrid_search(
        workspace_id=workspace_id,
        query_vector=query_vector,
        query_text=query,
        limit=fusion_limit,
        filters=filters,
    )

    if not candidates:
        return []

    # Step 3: Generate snippets BEFORE reranking (reranker needs actual content)
    for c in candidates:
        file_path = Path(c["file_path"])
        snippet, stale = generate_snippet(
            file_path,
            c["start_line"],
            c["end_line"],
            project_root,
            chunk_hash=c.get("chunk_hash"),
        )
        c["snippet"] = snippet
        c["stale"] = stale

    # Step 4: Optional rerank
    if effective_mode == "quality" and len(candidates) > 0:
        # Get document texts for reranking
        doc_texts = [c["snippet"] for c in candidates]

        try:
            ranked = await rerank(query, doc_texts, instruction, config)
            # Reorder candidates by rerank score
            reordered = [(candidates[idx], score) for idx, score in ranked]
            reordered.sort(key=lambda x: x[1], reverse=True)
            candidates = [c for c, _ in reordered[:top_k]]
            # Add rerank_score to signals
            for c, score in reordered[:top_k]:
                c["signals"]["rerank_score"] = score
        except Exception:
            # Fallback to fusion order on rerank failure
            candidates = candidates[:top_k]
    else:
        candidates = candidates[:top_k]

    # Step 5: Build final results
    results: list[SearchResult] = []
    for c in candidates:
        file_path = Path(c["file_path"])

        results.append(
            SearchResult(
                repo_id=repo_id,
                workspace_id=workspace_id,
                path=file_path,
                start_line=c["start_line"],
                end_line=c["end_line"],
                snippet=c["snippet"],
                score=c.get("score", 0.0),
                stale=c.get("stale", False),
                source=f"{file_path}#L{c['start_line']}-L{c['end_line']}",
                signals=c.get("signals", {}),
            )
        )

    return results
