"""Chunking strategies for different file types."""

from __future__ import annotations

from pathlib import Path

from probe.chunking.text import chunk_lines, chunk_markdown
from probe.chunking.tree_sitter import SUPPORTED_LANGUAGES, chunk_with_tree_sitter
from probe.types import Chunk, ChunkKind


def detect_language(path: Path) -> str | None:
    """Detect language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "c_sharp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".lua": "lua",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".r": "r",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".vue": "vue",
        ".svelte": "svelte",
        ".zig": "zig",
        ".nim": "nim",
        ".ex": "elixir",
        ".exs": "elixir",
        ".erl": "erlang",
        ".hs": "haskell",
        ".ml": "ocaml",
        ".clj": "clojure",
        ".lisp": "commonlisp",
        ".el": "elisp",
    }
    return ext_map.get(path.suffix.lower())


def detect_kind(path: Path) -> ChunkKind:
    """Detect chunk kind from file path."""
    name = path.name.lower()
    suffix = path.suffix.lower()

    # Documentation
    if suffix in {".md", ".rst", ".txt", ".adoc"}:
        return ChunkKind.DOC

    # Config files
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}:
        return ChunkKind.CONFIG
    if name in {"dockerfile", "makefile", ".gitignore", ".env.example"}:
        return ChunkKind.CONFIG

    return ChunkKind.CODE


def chunk_file(content: str, path: Path) -> list[Chunk]:
    """Chunk a file using the appropriate strategy."""
    language = detect_language(path)
    kind = detect_kind(path)

    # Try tree-sitter for supported languages
    if language and language in SUPPORTED_LANGUAGES:
        chunks = chunk_with_tree_sitter(content, path, language)
        if chunks:
            return chunks

    # Markdown gets heading-based chunking
    if kind == ChunkKind.DOC and path.suffix.lower() == ".md":
        return chunk_markdown(content, path)

    # Fallback to line-based chunking
    return chunk_lines(content, path, kind=kind)


__all__ = ["chunk_file", "detect_language", "detect_kind", "SUPPORTED_LANGUAGES"]
