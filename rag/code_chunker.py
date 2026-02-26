"""
AST-aware code chunking for RAG.

Each function/class = one chunk (NOT 400-char text splits).
Preserves imports, decorators, and docstrings.
"""

import ast
import hashlib
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class CodeChunk:
    """A single semantic unit of code (function, class, or module)."""

    text: str
    metadata: dict = field(default_factory=dict)
    # metadata keys: repo, file_path, symbol_name, symbol_type,
    #                line_start, line_end, language

    def to_dict(self) -> dict:
        return {"text": self.text, "metadata": self.metadata}


# ─── Python Chunker ──────────────────────────────────────────


def chunk_python_file(
    source: str, file_path: str, repo: str
) -> list[CodeChunk]:
    """Split a Python file into function/class-level chunks."""
    chunks = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback: entire file as one chunk
        return [
            CodeChunk(
                text=source,
                metadata={
                    "repo": repo,
                    "file_path": file_path,
                    "symbol_name": file_path,
                    "symbol_type": "file",
                    "language": "python",
                },
            )
        ]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            segment = ast.get_source_segment(source, node)
            if segment and len(segment.strip()) > 20:
                sym_type = "class" if isinstance(node, ast.ClassDef) else "function"
                chunks.append(
                    CodeChunk(
                        text=segment,
                        metadata={
                            "repo": repo,
                            "file_path": file_path,
                            "symbol_name": node.name,
                            "symbol_type": sym_type,
                            "line_start": node.lineno,
                            "line_end": node.end_lineno,
                            "language": "python",
                        },
                    )
                )

    # If file has no functions/classes, chunk the whole file
    if not chunks:
        chunks.append(
            CodeChunk(
                text=source,
                metadata={
                    "repo": repo,
                    "file_path": file_path,
                    "symbol_name": file_path,
                    "symbol_type": "module",
                    "language": "python",
                },
            )
        )

    return deduplicate(chunks)


# ─── Generic Chunker (JS/TS/Go) ─────────────────────────────


# Simple regex patterns for non-Python languages
_JS_FUNC_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
_JS_CLASS_RE = re.compile(
    r"(?:export\s+)?class\s+(\w+)", re.MULTILINE
)
_GO_FUNC_RE = re.compile(
    r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.MULTILINE
)


def chunk_generic_file(
    source: str, file_path: str, repo: str, language: str
) -> list[CodeChunk]:
    """
    Regex-based chunking for JS/TS/Go files.
    Less precise than AST but good enough for RAG retrieval.
    """
    chunks = []
    lines = source.splitlines()

    # Pick patterns by language
    if language in ("javascript", "typescript"):
        func_re = _JS_FUNC_RE
        class_re = _JS_CLASS_RE
    elif language == "go":
        func_re = _GO_FUNC_RE
        class_re = None  # Go doesn't have classes
    else:
        # Unknown language: whole file as one chunk
        return [
            CodeChunk(
                text=source,
                metadata={
                    "repo": repo,
                    "file_path": file_path,
                    "symbol_name": file_path,
                    "symbol_type": "file",
                    "language": language,
                },
            )
        ]

    # Find function boundaries
    for match in func_re.finditer(source):
        name = match.group(1)
        start_pos = match.start()
        line_start = source[:start_pos].count("\n") + 1

        # Find the end of the function (brace matching for JS/Go)
        end_line = _find_block_end(lines, line_start - 1)
        segment = "\n".join(lines[line_start - 1 : end_line])

        if len(segment.strip()) > 20:
            chunks.append(
                CodeChunk(
                    text=segment,
                    metadata={
                        "repo": repo,
                        "file_path": file_path,
                        "symbol_name": name,
                        "symbol_type": "function",
                        "line_start": line_start,
                        "line_end": end_line,
                        "language": language,
                    },
                )
            )

    # Find classes (JS/TS only)
    if class_re:
        for match in class_re.finditer(source):
            name = match.group(1)
            start_pos = match.start()
            line_start = source[:start_pos].count("\n") + 1
            end_line = _find_block_end(lines, line_start - 1)
            segment = "\n".join(lines[line_start - 1 : end_line])

            if len(segment.strip()) > 20:
                chunks.append(
                    CodeChunk(
                        text=segment,
                        metadata={
                            "repo": repo,
                            "file_path": file_path,
                            "symbol_name": name,
                            "symbol_type": "class",
                            "line_start": line_start,
                            "line_end": end_line,
                            "language": language,
                        },
                    )
                )

    if not chunks:
        chunks.append(
            CodeChunk(
                text=source,
                metadata={
                    "repo": repo,
                    "file_path": file_path,
                    "symbol_name": file_path,
                    "symbol_type": "module",
                    "language": language,
                },
            )
        )

    return deduplicate(chunks)


def _find_block_end(lines: list[str], start_idx: int) -> int:
    """Find end of a brace-delimited block (JS/TS/Go)."""
    depth = 0
    found_open = False
    for i in range(start_idx, min(start_idx + 500, len(lines))):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
                if found_open and depth == 0:
                    return i + 1
    return min(start_idx + 50, len(lines))


# ─── Language Detection ──────────────────────────────────────

_EXT_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
}


def detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return _EXT_MAP.get(ext)


# ─── Unified Entry Point ─────────────────────────────────────


def chunk_file(source: str, file_path: str, repo: str) -> list[CodeChunk]:
    """Chunk any supported file using the appropriate strategy."""
    lang = detect_language(file_path)
    if lang == "python":
        return chunk_python_file(source, file_path, repo)
    elif lang:
        return chunk_generic_file(source, file_path, repo, lang)
    else:
        # Unsupported language: skip
        return []


# ─── Deduplication ────────────────────────────────────────────


def deduplicate(chunks: list[CodeChunk]) -> list[CodeChunk]:
    """Remove duplicate chunks by content hash."""
    seen: set[str] = set()
    result: list[CodeChunk] = []
    for c in chunks:
        h = hashlib.sha256(c.text.lower().strip().encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            result.append(c)
    return result
