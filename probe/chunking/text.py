"""Text-based chunking for markdown and fallback."""

from __future__ import annotations

import re
from pathlib import Path

from probe.types import Chunk, ChunkKind

# Chunk size settings
DEFAULT_CHUNK_LINES = 150
DEFAULT_OVERLAP_LINES = 30
MIN_CHUNK_LINES = 10


def chunk_markdown(content: str, path: Path) -> list[Chunk]:
    """Chunk markdown by headings."""
    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[Chunk] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    current_start = 0
    current_heading = "(intro)"

    for i, line in enumerate(lines):
        match = heading_pattern.match(line)
        if match:
            # Save previous section if it has content
            if i > current_start:
                section_lines = lines[current_start:i]
                section_content = "\n".join(section_lines)
                if section_content.strip():
                    chunks.append(
                        Chunk(
                            file_path=path,
                            start_line=current_start + 1,
                            end_line=i,
                            content=section_content,
                            language="markdown",
                            kind=ChunkKind.DOC,
                            symbol=current_heading,
                        )
                    )

            current_start = i
            current_heading = match.group(2).strip()

    # Don't forget the last section
    if current_start < len(lines):
        section_lines = lines[current_start:]
        section_content = "\n".join(section_lines)
        if section_content.strip():
            chunks.append(
                Chunk(
                    file_path=path,
                    start_line=current_start + 1,
                    end_line=len(lines),
                    content=section_content,
                    language="markdown",
                    kind=ChunkKind.DOC,
                    symbol=current_heading,
                )
            )

    # If no headings found, treat as single chunk
    if not chunks and content.strip():
        chunks.append(
            Chunk(
                file_path=path,
                start_line=1,
                end_line=len(lines),
                content=content,
                language="markdown",
                kind=ChunkKind.DOC,
                symbol=None,
            )
        )

    return chunks


def chunk_lines(
    content: str,
    path: Path,
    chunk_size: int = DEFAULT_CHUNK_LINES,
    overlap: int = DEFAULT_OVERLAP_LINES,
    kind: ChunkKind = ChunkKind.CODE,
) -> list[Chunk]:
    """Fallback line-based chunking with overlap."""
    lines = content.splitlines()
    if not lines:
        return []

    # For small files, return as single chunk
    if len(lines) <= chunk_size:
        return [
            Chunk(
                file_path=path,
                start_line=1,
                end_line=len(lines),
                content=content,
                language=None,
                kind=kind,
                symbol=None,
            )
        ]

    chunks: list[Chunk] = []
    i = 0

    while i < len(lines):
        end = min(i + chunk_size, len(lines))
        chunk_lines_slice = lines[i:end]
        chunk_content = "\n".join(chunk_lines_slice)

        chunks.append(
            Chunk(
                file_path=path,
                start_line=i + 1,
                end_line=end,
                content=chunk_content,
                language=None,
                kind=kind,
                symbol=None,
            )
        )

        if end >= len(lines):
            break

        # Move forward, keeping overlap
        i = end - overlap

    return chunks


__all__ = ["chunk_markdown", "chunk_lines"]
