"""AST-aware chunking using tree-sitter."""

from __future__ import annotations

from pathlib import Path

from probe.types import Chunk, ChunkKind

# Languages supported by tree-sitter-language-pack
# See: https://pypi.org/project/tree-sitter-language-pack/
SUPPORTED_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "tsx",
    "jsx",
    "rust",
    "go",
    "java",
    "c",
    "cpp",
    "c_sharp",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "lua",
    "bash",
    "r",
    "sql",
    "html",
    "css",
    "scss",
    "vue",
    "svelte",
    "zig",
    "nim",
    "elixir",
    "erlang",
    "haskell",
    "ocaml",
    "clojure",
    "commonlisp",
    "elisp",
}

# Node types that represent semantic units (functions, classes, etc.)
SEMANTIC_NODES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {
        "function_declaration", "class_declaration", "arrow_function", "method_definition"
    },
    "typescript": {
        "function_declaration", "class_declaration", "arrow_function", "method_definition"
    },
    "tsx": {
        "function_declaration", "class_declaration", "arrow_function", "method_definition"
    },
    "rust": {"function_item", "impl_item", "struct_item", "enum_item", "trait_item"},
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "java": {"method_declaration", "class_declaration", "interface_declaration"},
    "c": {"function_definition", "struct_specifier"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier"},
}

# Min/max lines for chunks
MIN_CHUNK_LINES = 20
MAX_CHUNK_LINES = 250


def chunk_with_tree_sitter(content: str, path: Path, language: str) -> list[Chunk]:
    """Chunk code using tree-sitter AST parsing."""
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        # tree-sitter-language-pack not installed
        return []

    try:
        parser = get_parser(language)
    except Exception:
        # Language not supported
        return []

    tree = parser.parse(content.encode())
    lines = content.splitlines()

    if not lines:
        return []

    chunks: list[Chunk] = []
    semantic_types = SEMANTIC_NODES.get(language, set())

    # Extract header chunk (imports, top-level constants)
    header_end = find_header_end(tree.root_node, lines)
    if header_end > 0:
        header_content = "\n".join(lines[:header_end])
        if len(header_content.strip()) > 0:
            chunks.append(
                Chunk(
                    file_path=path,
                    start_line=1,
                    end_line=header_end,
                    content=header_content,
                    language=language,
                    kind=ChunkKind.CODE,
                    symbol="(header)",
                )
            )

    # Extract semantic units
    for node in walk_tree(tree.root_node):
        if node.type in semantic_types:
            start_line = node.start_point[0] + 1  # 1-indexed
            end_line = node.end_point[0] + 1

            # Get symbol name
            symbol = extract_symbol_name(node, language)

            # Get content
            chunk_lines = lines[start_line - 1 : end_line]
            chunk_content = "\n".join(chunk_lines)

            # Handle very large functions by splitting
            if len(chunk_lines) > MAX_CHUNK_LINES:
                sub_chunks = split_large_chunk(
                    chunk_content, path, language, start_line, symbol
                )
                chunks.extend(sub_chunks)
            else:
                chunks.append(
                    Chunk(
                        file_path=path,
                        start_line=start_line,
                        end_line=end_line,
                        content=chunk_content,
                        language=language,
                        kind=ChunkKind.CODE,
                        symbol=symbol,
                    )
                )

    # If no semantic chunks found, fall back to line-based
    if not chunks:
        return []

    return chunks


def find_header_end(root_node, lines: list[str]) -> int:
    """Find where imports/top-level declarations end."""
    header_types = {"import_statement", "import_from_statement", "use_declaration", "include"}
    last_header_line = 0

    for child in root_node.children:
        if child.type in header_types:
            last_header_line = child.end_point[0] + 1
        elif child.type in {"comment", "line_comment", "block_comment"}:
            # Include leading comments in header
            if child.start_point[0] <= last_header_line + 2:
                last_header_line = child.end_point[0] + 1
        else:
            # Stop at first non-header node
            break

    return last_header_line


def walk_tree(node):
    """Walk tree-sitter AST yielding all nodes."""
    yield node
    for child in node.children:
        yield from walk_tree(child)


def extract_symbol_name(node, language: str) -> str | None:
    """Extract the name of a function/class from AST node."""
    # Look for identifier/name child
    for child in node.children:
        if child.type in {"identifier", "name", "property_identifier"}:
            return child.text.decode() if hasattr(child.text, "decode") else str(child.text)

    return None


def split_large_chunk(
    content: str,
    path: Path,
    language: str,
    start_line: int,
    symbol: str | None,
) -> list[Chunk]:
    """Split a large chunk into smaller overlapping pieces."""
    lines = content.splitlines()
    chunks: list[Chunk] = []

    chunk_size = 200
    overlap = 30
    i = 0

    while i < len(lines):
        end = min(i + chunk_size, len(lines))
        chunk_lines = lines[i:end]
        chunk_content = "\n".join(chunk_lines)

        chunks.append(
            Chunk(
                file_path=path,
                start_line=start_line + i,
                end_line=start_line + end - 1,
                content=chunk_content,
                language=language,
                kind=ChunkKind.CODE,
                symbol=f"{symbol}[part]" if symbol else None,
            )
        )

        if end >= len(lines):
            break
        i = end - overlap

    return chunks
