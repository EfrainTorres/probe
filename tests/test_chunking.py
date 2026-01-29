"""Tests for chunking module."""

from __future__ import annotations

from pathlib import Path

from probe.chunking import chunk_file, detect_kind, detect_language
from probe.chunking.text import chunk_lines, chunk_markdown
from probe.types import ChunkKind


class TestDetection:
    """Tests for language and kind detection."""

    def test_detect_python(self) -> None:
        assert detect_language(Path("foo.py")) == "python"

    def test_detect_typescript(self) -> None:
        assert detect_language(Path("bar.ts")) == "typescript"
        assert detect_language(Path("baz.tsx")) == "tsx"

    def test_detect_unknown(self) -> None:
        assert detect_language(Path("unknown.xyz")) is None

    def test_detect_kind_code(self) -> None:
        assert detect_kind(Path("main.py")) == ChunkKind.CODE

    def test_detect_kind_doc(self) -> None:
        assert detect_kind(Path("README.md")) == ChunkKind.DOC

    def test_detect_kind_config(self) -> None:
        assert detect_kind(Path("config.yaml")) == ChunkKind.CONFIG
        assert detect_kind(Path("Dockerfile")) == ChunkKind.CONFIG


class TestMarkdownChunking:
    """Tests for markdown chunking."""

    def test_chunk_by_headings(self, sample_markdown: str) -> None:
        chunks = chunk_markdown(sample_markdown, Path("README.md"))

        # Should have chunks for each heading
        assert len(chunks) >= 3

        # First chunk should be the intro/main title
        assert chunks[0].start_line == 1

        # All chunks should be DOC kind
        for chunk in chunks:
            assert chunk.kind == ChunkKind.DOC

    def test_empty_markdown(self) -> None:
        chunks = chunk_markdown("", Path("empty.md"))
        assert len(chunks) == 0

    def test_no_headings(self) -> None:
        content = "Just some text\nwithout any headings."
        chunks = chunk_markdown(content, Path("plain.md"))
        assert len(chunks) == 1


class TestLineChunking:
    """Tests for line-based chunking."""

    def test_small_file_single_chunk(self) -> None:
        content = "line1\nline2\nline3"
        chunks = chunk_lines(content, Path("small.txt"))

        assert len(chunks) == 1
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 3

    def test_large_file_multiple_chunks(self) -> None:
        # Create content larger than default chunk size
        lines = [f"line {i}" for i in range(200)]
        content = "\n".join(lines)

        chunks = chunk_lines(content, Path("large.txt"), chunk_size=50, overlap=10)

        assert len(chunks) > 1

        # Chunks should overlap
        for i in range(len(chunks) - 1):
            assert chunks[i + 1].start_line <= chunks[i].end_line


class TestChunkFile:
    """Integration tests for chunk_file."""

    def test_chunk_python_file(self, sample_python_code: str) -> None:
        chunks = chunk_file(sample_python_code, Path("sample.py"))

        # Should produce chunks
        assert len(chunks) > 0

        # All should be CODE kind
        for chunk in chunks:
            assert chunk.kind == ChunkKind.CODE
            assert chunk.language == "python"

    def test_chunk_markdown_file(self, sample_markdown: str) -> None:
        chunks = chunk_file(sample_markdown, Path("README.md"))

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.kind == ChunkKind.DOC
