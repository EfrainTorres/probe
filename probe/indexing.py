"""Indexing pipeline: scan -> chunk -> embed -> store."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid5

import httpx

from probe.chunking import chunk_file
from probe.config import ProbeConfig
from probe.storage import Manifest, QdrantClient
from probe.types import IndexedChunk

# Namespace for deterministic UUIDs
NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def compute_point_id(workspace_id: UUID, file_path: Path, start_line: int, end_line: int) -> UUID:
    """Compute deterministic point ID from position (not content)."""
    key = f"{workspace_id}:{file_path}:{start_line}:{end_line}"
    return uuid5(NAMESPACE, key)


def compute_chunk_hash(content: str) -> str:
    """Compute truncated hash for staleness detection."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_file_hash(path: Path) -> str:
    """Compute file hash for change detection."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def embed_texts(texts: list[str], config: ProbeConfig) -> list[list[float]]:
    """Get embeddings from TEI service."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config.tei_url}/embed",
            json={"inputs": texts},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def scan_files(project_root: Path) -> AsyncIterator[Path]:
    """Enumerate files respecting .gitignore and default ignores."""
    # Default ignore patterns
    ignore_patterns = {
        ".git",
        ".probe",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
    }

    for path in project_root.rglob("*"):
        if not path.is_file():
            continue

        # Skip ignored directories
        parts = path.relative_to(project_root).parts
        if any(p in ignore_patterns or p.startswith(".") for p in parts[:-1]):
            continue

        # Skip binary/large files
        if path.suffix in {".exe", ".dll", ".so", ".dylib", ".bin", ".dat"}:
            continue

        yield path


async def index_file(
    file_path: Path,
    project_root: Path,
    repo_id: str,
    workspace_id: UUID,
    config: ProbeConfig,
    qdrant: QdrantClient,
    manifest: Manifest,
) -> int:
    """Index a single file. Returns number of chunks indexed."""
    relative_path = file_path.relative_to(project_root)

    # Check if file needs reindexing
    stat = file_path.stat()
    existing = await manifest.get_file(relative_path)

    if existing and existing["mtime"] == stat.st_mtime and existing["size"] == stat.st_size:
        # Fast skip - file unchanged
        return 0

    # File changed or new - reindex
    file_hash = compute_file_hash(file_path)

    # Delete existing chunks for this file
    await qdrant.delete_by_file(workspace_id, relative_path)
    await manifest.delete_file_chunks(relative_path)

    # Chunk the file
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        # Skip binary files
        return 0

    chunks = chunk_file(content, relative_path)

    if not chunks:
        return 0

    # Embed chunks
    texts = [c.content for c in chunks]
    embeddings = await embed_texts(texts, config)

    # Store in Qdrant and manifest
    indexed_chunks: list[IndexedChunk] = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
        point_id = compute_point_id(
            workspace_id, relative_path, chunk.start_line, chunk.end_line
        )
        chunk_hash = compute_chunk_hash(chunk.content)

        indexed = IndexedChunk(
            point_id=point_id,
            file_path=relative_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            chunk_hash=chunk_hash,
            chunk_idx=idx,
            language=chunk.language,
            kind=chunk.kind,
            symbol=chunk.symbol,
        )
        indexed_chunks.append(indexed)

        # Upsert to Qdrant
        await qdrant.upsert_chunk(
            point_id=point_id,
            repo_id=repo_id,
            workspace_id=workspace_id,
            file_path=relative_path,
            file_hash=file_hash,
            chunk=chunk,
            chunk_hash=chunk_hash,
            dense_vector=embedding,
        )

    # Update manifest
    await manifest.upsert_file(
        file_path=relative_path,
        mtime=stat.st_mtime,
        size=stat.st_size,
        file_hash=file_hash,
    )
    await manifest.upsert_chunks(indexed_chunks)

    return len(indexed_chunks)


async def run_scan(
    project_root: Path,
    repo_id: str,
    workspace_id: UUID,
    config: ProbeConfig,
    qdrant: QdrantClient,
    manifest: Manifest,
) -> dict[str, int]:
    """Run a full incremental scan. Returns stats."""
    files_scanned = 0
    chunks_indexed = 0

    async for file_path in scan_files(project_root):
        files_scanned += 1
        count = await index_file(
            file_path=file_path,
            project_root=project_root,
            repo_id=repo_id,
            workspace_id=workspace_id,
            config=config,
            qdrant=qdrant,
            manifest=manifest,
        )
        chunks_indexed += count

    return {
        "files_scanned": files_scanned,
        "chunks_indexed": chunks_indexed,
    }
