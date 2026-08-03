# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/parsing/chunker.py
-----------------------
Convert :class:`~app.parsing.tree_sitter_parser.ParsedFile` records into
embedding-ready :class:`CodeChunk` objects.

Responsibility boundary
-----------------------
This module receives a :class:`ParsedFile` from Module 5's parser and the
decoded file content from Module 4's :func:`~app.ingestion.file_filter.safe_decode`.
It does NOT:
  - clone, filter, or parse any source code (Modules 3-5),
  - embed chunks or write to any vector/BM25/graph store (Modules 6-7).

Pipeline per chunk (order is LOAD-BEARING — do not reorder)
------------------------------------------------------------
1. Extract raw source lines for the function/class span.
2. Prepend synthetic header (``# File: ... | Function: ...``).
3. **Mask secrets** — replace AWS keys, API tokens, password literals.
4. **Compute fingerprint** — sha256(normalized_path + function_name + *masked* text).

Why masking MUST come before fingerprinting
-------------------------------------------
Two functions that are identical except for a different leaked secret should
correctly deduplicate to *one* fingerprint — because after masking they really
are the same text.  If fingerprinting ran before masking, those two functions
would get different fingerprints and both would be stored, silently differing
only by which secret they leaked.

Fingerprint includes normalized_path
-------------------------------------
The fingerprint is ``sha256(normalized_path + "\\x00" + function_name + "\\x00" + masked_body)``.
Including ``normalized_path`` means two genuinely different files containing
identical boilerplate functions (e.g. identical ``__init__`` methods) produce
*different* fingerprints and are NOT collapsed — they live in separate files and
should both be stored and retrievable.  This is correct, expected dedup
behavior: dedup only applies within the same logical file.

Secret masking tradeoffs
------------------------
The masking regexes err toward over-redaction (false positives) rather than
under-redaction.  A long random-looking test fixture string might be incorrectly
masked.  This is an acceptable tradeoff for v1 — building a perfect secret
classifier is outside scope.

Token counting
--------------
Tokens are approximated as ``len(text) // 4`` (4 chars per token), which is
accurate enough for code at the chunk sizes used here.  This avoids a tiktoken
dependency; the approximation is noted clearly so a future maintainer can swap
in a real tokenizer.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.observability.logging_config import logger
from app.config import settings
from app.parsing.tree_sitter_parser import ParsedClass, ParsedFile, ParsedFunction

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

#: A class body shorter than this (in source lines) is emitted as one chunk.
#: At or above this threshold its methods are chunked individually.
MAX_CLASS_LINES_BEFORE_SPLIT: int = 80

# ---------------------------------------------------------------------------
# Secret masking patterns (applied BEFORE fingerprinting — see module docstring)
# ---------------------------------------------------------------------------

# AWS Access Key ID — always starts with AKIA followed by exactly 16 uppercase
# alphanumeric characters.
_AWS_KEY_PATTERN = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

# API key / secret / token in assignment context.
# Captures the VALUE between quotes; the key name and quote chars are preserved.
# Group 1 = opening delimiter, Group 2 = the secret value, Group 3 = closing delimiter.
_API_TOKEN_PATTERN = re.compile(
    r"((?:api[_-]?key|api[_-]?secret|auth[_-]?token|access[_-]?token|"
    r"secret[_-]?key|private[_-]?key|client[_-]?secret|bearer)"
    r"\s*(?:=|:)\s*[\"'])"
    r"([A-Za-z0-9\-_\.+/=]{16,})"
    r"([\"'])",
    re.IGNORECASE,
)

# Password in assignment context.
# Group 1 = key + quote, Group 2 = the secret value, Group 3 = closing quote.
_PASSWORD_PATTERN = re.compile(
    r"((?:password|passwd|pwd)\s*(?:=|:)\s*[\"'])"
    r"([^\"']{8,})"
    r"([\"'])",
    re.IGNORECASE,
)


def mask_secrets(text: str) -> str:
    """
    Replace secret-shaped strings in *text* with ``[REDACTED]``.

    This function MUST run before fingerprinting and before embedding.
    It is exposed as a public function (not buried in the chunk loop) so it
    can be unit-tested and called independently.

    Patterns detected
    -----------------
    - AWS Access Key IDs (``AKIA...``).
    - API key / token / secret assignments (``api_key = "..."``).
    - Password assignments (``password = "..."``).

    False-positive policy
    ---------------------
    Errs toward over-redaction.  A long random-looking test fixture string
    may be incorrectly masked.  This is intentional and documented: building
    a perfect secret classifier is explicitly out of scope for v1.
    """
    # Replace AWS key IDs wholesale
    text = _AWS_KEY_PATTERN.sub("[REDACTED]", text)

    # Replace just the VALUE in API token assignments (preserve key name + quotes)
    text = _API_TOKEN_PATTERN.sub(r"\1[REDACTED]\3", text)

    # Replace just the VALUE in password assignments
    text = _PASSWORD_PATTERN.sub(r"\1[REDACTED]\3", text)

    return text


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def compute_fingerprint(
    normalized_path: str,
    function_name: str,
    masked_body: str,
) -> str:
    """
    Return a sha256 fingerprint for a chunk.

    **Always call this AFTER** :func:`mask_secrets` — the fingerprint is
    computed on masked text so that two copies of the same function differing
    only by a different secret collapse to one fingerprint.

    The fingerprint includes *normalized_path* so that two genuinely different
    files containing identical boilerplate functions (e.g. two ``__init__``
    methods) are NOT collapsed — they belong to different files.
    """
    raw = f"{normalized_path}\x00{function_name}\x00{masked_body}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Token counting (approximation)
# ---------------------------------------------------------------------------

def count_tokens_approx(text: str) -> int:
    """
    Approximate token count: ``len(text) // 4``.

    Code averages ~4 characters per token for common embedding models.
    This avoids a tiktoken / sentencepiece dependency.  The approximation is
    noted here so a future maintainer can drop in a real tokenizer.
    """
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Text splitting with overlap
# ---------------------------------------------------------------------------

def split_with_overlap(
    text: str,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[str]:
    """
    Split *text* into pieces of at most *max_tokens*, with *overlap_tokens*
    overlap between adjacent pieces.

    Splits prefer line boundaries to avoid cutting in the middle of a statement.
    Returns a list of strings; if the text fits within *max_tokens*, the list
    has exactly one element (the original text).
    """
    max_tokens = max_tokens or settings.CHUNK_MAX_TOKENS
    overlap_tokens = overlap_tokens or settings.CHUNK_OVERLAP_TOKENS

    if count_tokens_approx(text) <= max_tokens:
        return [text]

    max_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4

    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        if current_len + len(line) > max_chars and current:
            chunk_text = "".join(current)
            chunks.append(chunk_text)

            # Build the overlap window from the tail of the current chunk
            overlap_lines: list[str] = []
            acc = 0
            for l in reversed(current):
                if acc + len(l) > overlap_chars:
                    break
                overlap_lines.insert(0, l)
                acc += len(l)

            current = overlap_lines + [line]
            current_len = sum(len(l) for l in current)
        else:
            current.append(line)
            current_len += len(line)

    if current:
        chunks.append("".join(current))

    return chunks or [text]


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class CodeChunk:
    """
    A single embedding-ready code chunk.

    ``chunk_text`` is what gets passed to the embedding model — it already
    contains the synthetic header, has had secrets masked, and is at most
    ``settings.CHUNK_MAX_TOKENS`` tokens long.

    Module 6 treats all fields as final and will NOT re-mask, re-fingerprint,
    or re-derive metadata from this record.
    """
    chunk_text: str           # synthetic header + masked body (ready to embed)
    file_path: str            # absolute path (for reading; not embedded)
    display_path: str         # original casing, relative (for user-facing output)
    normalized_path: str      # lowercase, relative (for hashing and dedup keys)
    function_name: str        # function or class name
    start_line: int
    end_line: int
    type: str                 # "function" | "class" | "method"
    language: str             # python | javascript | typescript
    fingerprint: str          # sha256(normalized_path + function_name + masked_body)
    class_name: str | None    # set only when type == "method"

    @property
    def token_count(self) -> int:
        return get_token_count(self.chunk_text)


# ---------------------------------------------------------------------------
# Internal chunk builders
# ---------------------------------------------------------------------------

def _extract_lines(content: str, start_line: int, end_line: int) -> str:
    """
    Return source lines *start_line*‥*end_line* (1-indexed, inclusive) from *content*.

    If the line numbers are out of bounds (edge case with very short files or
    off-by-one in tree-sitter output), returns whatever lines are available.
    """
    lines = content.splitlines()
    return "\n".join(lines[max(0, start_line - 1) : end_line])


def _get_module_header(content: str, max_lines: int = 15) -> str:
    """
    Extract a compact module header (imports, top-level constants, docstrings)
    from the beginning of *content*.
    """
    if not content or not content.strip():
        return ""
    lines = content.splitlines()
    header_lines = []
    for line in lines[:max_lines]:
        stripped = line.strip()
        # Stop if we hit a function or class definition
        if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("export default function"):
            break
        if (stripped.startswith("import ") or stripped.startswith("from ") or
            stripped.startswith("#") or stripped.startswith("//") or
            "=" in stripped or stripped.startswith('"""') or stripped.startswith("'''") or
            stripped == ""):
            header_lines.append(line)
    if not header_lines:
        return ""
    res = "\n".join(header_lines).strip()
    if len(res) > 400:
        res = res[:400] + "\n..."
    return res


def _make_chunks(
    *,
    raw_body: str,
    header: str,
    module_header: str = "",
    file_path: str,
    display_path: str,
    normalized_path: str,
    function_name: str,
    start_line: int,
    end_line: int,
    chunk_type: str,
    language: str,
    class_name: str | None,
) -> list[CodeChunk]:
    """
    Core chunk factory.

    Order of operations (load-bearing — do not reorder):
    1. Prepend synthetic header and optional compact module header to raw body.
    2. Mask secrets on the full text (header + body).
    3. Split if over token limit.
    4. Compute fingerprint on each masked piece.
    """
    if module_header:
        full_text = f"{header}\n# Module Context:\n{module_header}\n\n{raw_body}"
    else:
        full_text = f"{header}\n{raw_body}"

    # ── Step 2: mask secrets before ANYTHING else ────────────────────────────
    masked_text = mask_secrets(full_text)

    # ── Step 3: split if needed ──────────────────────────────────────────────
    pieces = split_with_overlap(masked_text)

    chunks: list[CodeChunk] = []
    for i, piece in enumerate(pieces):
        # ── Step 4: fingerprint on masked text ───────────────────────────────
        fp = compute_fingerprint(normalized_path, function_name, piece)
        chunks.append(
            CodeChunk(
                chunk_text=piece,
                file_path=file_path,
                display_path=display_path,
                normalized_path=normalized_path,
                function_name=function_name if len(pieces) == 1
                else f"{function_name}[part {i + 1}/{len(pieces)}]",
                start_line=start_line,
                end_line=end_line,
                type=chunk_type,
                language=language,
                fingerprint=fp,
                class_name=class_name,
            )
        )

    return chunks


def _chunk_function(
    func: ParsedFunction,
    content: str,
    language: str,
    file_path: str,
    display_path: str,
    normalized_path: str,
) -> list[CodeChunk]:
    """Produce chunks for a top-level function."""
    body = _extract_lines(content, func.start_line, func.end_line)
    mod_header = _get_module_header(content) if func.start_line > 15 else ""
    header = f"# File: {display_path} | Function: {func.name}"
    return _make_chunks(
        raw_body=body,
        header=header,
        module_header=mod_header,
        file_path=file_path,
        display_path=display_path,
        normalized_path=normalized_path,
        function_name=func.name,
        start_line=func.start_line,
        end_line=func.end_line,
        chunk_type="function",
        language=language,
        class_name=None,
    )


def _chunk_method(
    method: ParsedFunction,
    class_name: str,
    content: str,
    language: str,
    file_path: str,
    display_path: str,
    normalized_path: str,
) -> list[CodeChunk]:
    """Produce chunks for a single class method (when class is large)."""
    body = _extract_lines(content, method.start_line, method.end_line)
    mod_header = _get_module_header(content) if method.start_line > 15 else ""
    header = f"# File: {display_path} | Class: {class_name}.{method.name}"
    return _make_chunks(
        raw_body=body,
        header=header,
        module_header=mod_header,
        file_path=file_path,
        display_path=display_path,
        normalized_path=normalized_path,
        function_name=method.name,
        start_line=method.start_line,
        end_line=method.end_line,
        chunk_type="method",
        language=language,
        class_name=class_name,
    )


def _chunk_class(
    cls: ParsedClass,
    content: str,
    language: str,
    file_path: str,
    display_path: str,
    normalized_path: str,
) -> list[CodeChunk]:
    """Produce chunks for an entire class (when class is small or has no methods)."""
    body = _extract_lines(content, cls.start_line, cls.end_line)
    mod_header = _get_module_header(content) if cls.start_line > 15 else ""
    header = f"# File: {display_path} | Class: {cls.name}"
    return _make_chunks(
        raw_body=body,
        header=header,
        module_header=mod_header,
        file_path=file_path,
        display_path=display_path,
        normalized_path=normalized_path,
        function_name=cls.name,
        start_line=cls.start_line,
        end_line=cls.end_line,
        chunk_type="class",
        language=language,
        class_name=None,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_parsed_file(
    parsed: ParsedFile,
    content: str,
    file_path: str,
    display_path: str,
    normalized_path: str,
) -> list[CodeChunk]:
    """
    Convert a :class:`~app.parsing.tree_sitter_parser.ParsedFile` into a list
    of :class:`CodeChunk` objects ready for Module 6's embedding step.

    Parameters
    ----------
    parsed:
        Output of :func:`~app.parsing.tree_sitter_parser.parse_file`.
    content:
        Full decoded file content (from Module 4's :func:`~app.ingestion.file_filter.safe_decode`).
    file_path:
        Absolute path to the file (``FileRecord.path``), carried through for
        Module 6 to read the file if needed.
    display_path:
        Original-casing relative path (``FileRecord.display_path``).
    normalized_path:
        Lowercase relative path (``FileRecord.normalized_path``).

    Returns
    -------
    list[CodeChunk]
        May be empty if the file has no functions or classes — this is not an
        error; a constants-only module legitimately produces zero chunks.

    Edge-case handling
    ------------------
    * Zero functions/classes → empty list, log a debug note, no crash.
    * Class with 0 methods but ≥ 200 lines → treated as one class chunk
      (documented fallback; cannot split what has no method boundaries).
    * 3-line functions → still get a header, still get fingerprinted.
    """
    log = logger.bind(
        file_path=display_path,
        language=parsed.language,
        n_functions=len(parsed.functions),
        n_classes=len(parsed.classes),
    )

    chunks: list[CodeChunk] = []

    # ── Top-level functions ───────────────────────────────────────────────────
    for func in parsed.functions:
        chunks.extend(
            _chunk_function(
                func, content, parsed.language,
                file_path, display_path, normalized_path,
            )
        )

    # ── Classes ──────────────────────────────────────────────────────────────
    for cls in parsed.classes:
        cls_lines = cls.end_line - cls.start_line + 1

        if cls_lines >= MAX_CLASS_LINES_BEFORE_SPLIT and cls.methods:
            # Large class with methods → chunk methods individually.
            # Each method chunk carries class_name so the relationship is preserved.
            for method in cls.methods:
                chunks.extend(
                    _chunk_method(
                        method, cls.name, content, parsed.language,
                        file_path, display_path, normalized_path,
                    )
                )
        else:
            # Small class OR large class with no splittable methods.
            # Fallback for large no-method classes: treat as one chunk regardless
            # of size.  Rationale: there are no method boundaries to split on;
            # the alternative (raw line split) would break the "never raw line
            # splits" chunking contract.
            chunks.extend(
                _chunk_class(
                    cls, content, parsed.language,
                    file_path, display_path, normalized_path,
                )
            )

    # ── Top-level module chunk (imports, constants, module docstrings) ─────────────
    mod_header = _get_module_header(content, max_lines=40)
    if mod_header and len(mod_header) > 20:
        mod_fp = compute_fingerprint(normalized_path, "module_header", mod_header)
        mod_chunk = CodeChunk(
            chunk_text=f"# File: {display_path} | Module Header & Constants\n{mod_header}",
            file_path=file_path,
            display_path=display_path,
            normalized_path=normalized_path,
            function_name="<module>",
            start_line=1,
            end_line=min(40, len(content.splitlines())),
            type="module",
            language=parsed.language,
            fingerprint=mod_fp,
            class_name=None,
        )
        chunks.insert(0, mod_chunk)

    if not chunks:
        log.debug(
            "no_chunks_produced",
            hint="File has no top-level functions or classes (e.g. constants-only module). "
                 "This is not an error.",
        )

    log.info(
        "file_chunked",
        n_chunks=len(chunks),
    )

    return chunks


def chunk_all_files(
    parsed_files: Sequence[ParsedFile | None],
    contents: dict[str, str],
    file_records: dict[str, tuple[str, str, str]],
) -> list[CodeChunk]:
    """
    Batch-chunk multiple parsed files.

    Parameters
    ----------
    parsed_files:
        Sequence of :class:`ParsedFile` or ``None`` (parse failures).
        ``None`` entries are silently skipped.
    contents:
        ``{display_path: decoded_content}`` mapping.
    file_records:
        ``{display_path: (file_path, display_path, normalized_path)}`` mapping.

    Returns
    -------
    list[CodeChunk]
        All chunks from all files, deduplicated by fingerprint.
    """
    seen_fingerprints: set[str] = set()
    all_chunks: list[CodeChunk] = []

    for parsed in parsed_files:
        if parsed is None:
            continue
        content = contents.get(parsed.file_path, "")
        if not content:
            continue
        record = file_records.get(parsed.file_path)
        if record is None:
            continue
        file_path, display_path, normalized_path = record

        for chunk in chunk_parsed_file(
            parsed, content, file_path, display_path, normalized_path
        ):
            if chunk.fingerprint not in seen_fingerprints:
                seen_fingerprints.add(chunk.fingerprint)
                all_chunks.append(chunk)

    logger.info(
        "all_files_chunked",
        total_chunks=len(all_chunks),
        total_files=sum(1 for p in parsed_files if p is not None),
    )

    return all_chunks


# ---------------------------------------------------------------------------
# Module #11 Additions: AST-aware chunking and packing
# ---------------------------------------------------------------------------

class Chunk:
    """
    A chunk object returned by chunk_definitions.
    Conforms to the data contract: {text, metadata, token_count}.
    """
    def __init__(self, text: str, metadata: dict[str, Any], token_count: int):
        self.text = text
        self.metadata = metadata
        self.token_count = token_count

    # Properties to support downstream compatibility with CodeChunk
    @property
    def chunk_text(self) -> str:
        return self.text

    @property
    def fingerprint(self) -> str:
        return self.metadata.get("fingerprint", "")

    @property
    def file_path(self) -> str:
        return self.metadata.get("file_path", "")

    @property
    def display_path(self) -> str:
        return self.metadata.get("display_path", "")

    @property
    def normalized_path(self) -> str:
        return self.metadata.get("normalized_path", "")

    @property
    def function_name(self) -> str:
        return self.metadata.get("function_name", "")

    @property
    def start_line(self) -> int:
        return self.metadata.get("start_line", 0)

    @property
    def end_line(self) -> int:
        return self.metadata.get("end_line", 0)

    @property
    def type(self) -> str:
        return self.metadata.get("type", "")

    @property
    def language(self) -> str:
        return self.metadata.get("language", "")

    @property
    def class_name(self) -> str | None:
        return self.metadata.get("class_name", None)


def get_token_count(text: str) -> int:
    """
    Count tokens using tiktoken (cl100k_base).
    Falls back to whitespace/character approximation if tiktoken is not available.
    """
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def build_chunk_metadata(chunk: Any) -> dict[str, Any]:
    """
    Build metadata for a chunk to be cited back to the user as a source.
    """
    if hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
        metadata = chunk.metadata
    else:
        metadata = {}

    file_path = getattr(chunk, "file_path", metadata.get("file_path", ""))
    start_line = getattr(chunk, "start_line", metadata.get("start_line", 0))
    end_line = getattr(chunk, "end_line", metadata.get("end_line", 0))
    language = getattr(chunk, "language", metadata.get("language", ""))

    definition_names = metadata.get("definition_names", [])
    if not definition_names:
        func_name = getattr(chunk, "function_name", metadata.get("function_name", ""))
        if func_name:
            definition_names = [func_name]

    return {
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "definition_names": definition_names,
        "language": language,
    }


def get_statement_segments(
    file_path: str,
    content: str,
    start_line: int,
    end_line: int,
    language: str,
    parent_name: str,
    parent_type: str,
) -> list[dict[str, Any]]:
    """
    Extract child statements within the given range using tree-sitter AST.
    """
    from app.parsing.tree_sitter_parser import get_parser
    parser = None
    try:
        parser = get_parser(language)
    except Exception:
        pass
    if not parser:
        return []

    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception:
        return []

    target_node = None
    min_diff = 999999

    def find_target(node):
        nonlocal target_node, min_diff
        s = node.start_point[0] + 1
        e = node.end_point[0] + 1
        if s <= end_line and e >= start_line:
            if node.type in (
                "function_definition", "class_definition", 
                "function_declaration", "class_declaration", 
                "method_definition", "struct_item", "impl_item"
            ):
                diff = abs(s - start_line)
                if diff < min_diff:
                    min_diff = diff
                    target_node = node
            for child in node.named_children:
                find_target(child)

    find_target(tree.root_node)
    if not target_node:
        return []

    block_node = None
    for child in target_node.named_children:
        if child.type in ("block", "statement_block"):
            block_node = child
            break

    if not block_node:
        block_node = target_node

    statement_nodes = [c for c in block_node.named_children]
    if not statement_nodes:
        return []

    statement_nodes.sort(key=lambda n: n.start_point[0])

    segments = []
    lines = content.splitlines()

    current_line = start_line
    for node in statement_nodes:
        n_start = node.start_point[0] + 1
        n_end = node.end_point[0] + 1

        if n_start > current_line:
            gap_text = "\n".join(lines[current_line - 1 : n_start - 1])
            if gap_text.strip():
                segments.append({
                    "text": gap_text,
                    "start_line": current_line,
                    "end_line": n_start - 1,
                    "names": [parent_name],
                    "type": parent_type,
                })

        clamped_end = min(n_end, end_line)
        if clamped_end >= n_start:
            node_text = "\n".join(lines[n_start - 1 : clamped_end])
            segments.append({
                "text": node_text,
                "start_line": n_start,
                "end_line": clamped_end,
                "names": [parent_name],
                "type": parent_type,
            })
            current_line = clamped_end + 1

    if current_line <= end_line:
        epilogue_text = "\n".join(lines[current_line - 1 : end_line])
        if epilogue_text.strip():
            segments.append({
                "text": epilogue_text,
                "start_line": current_line,
                "end_line": end_line,
                "names": [parent_name],
                "type": parent_type,
            })

    return segments


def split_non_def_segment(
    text: str,
    start: int,
    end: int,
    parent_def: dict[str, Any],
    max_tokens: int,
    file_content: str | None,
) -> list[dict[str, Any]]:
    """
    Split a segment of code that is not a definition.
    """
    if get_token_count(text) <= max_tokens:
        return [{
            "text": text,
            "start_line": start,
            "end_line": end,
            "names": [parent_def["name"]],
            "type": parent_def["type"],
            "class_name": parent_def.get("class_name"),
        }]

    language = parent_def.get("language", "")
    if file_content and language:
        stmt_segs = get_statement_segments(
            file_path=parent_def.get("file_path", ""),
            content=file_content,
            start_line=start,
            end_line=end,
            language=language,
            parent_name=parent_def["name"],
            parent_type=parent_def["type"],
        )
        if stmt_segs:
            res = []
            for seg in stmt_segs:
                if get_token_count(seg["text"]) <= max_tokens:
                    res.append({
                        "text": seg["text"],
                        "start_line": seg["start_line"],
                        "end_line": seg["end_line"],
                        "names": seg["names"],
                        "type": seg["type"],
                        "class_name": parent_def.get("class_name"),
                    })
                else:
                    pieces = split_with_overlap(seg["text"], max_tokens=max_tokens)
                    lines_in_piece = max(1, (seg["end_line"] - seg["start_line"] + 1) // len(pieces))
                    for idx, piece in enumerate(pieces):
                        p_start = seg["start_line"] + idx * lines_in_piece
                        p_end = min(seg["end_line"], p_start + lines_in_piece - 1) if idx < len(pieces) - 1 else seg["end_line"]
                        res.append({
                            "text": piece,
                            "start_line": p_start,
                            "end_line": p_end,
                            "names": seg["names"],
                            "type": seg["type"],
                            "class_name": parent_def.get("class_name"),
                        })
            return res

    pieces = split_with_overlap(text, max_tokens=max_tokens)
    res = []
    lines_in_piece = max(1, (end - start + 1) // len(pieces))
    for idx, piece in enumerate(pieces):
        p_start = start + idx * lines_in_piece
        p_end = min(end, p_start + lines_in_piece - 1) if idx < len(pieces) - 1 else end
        res.append({
            "text": piece,
            "start_line": p_start,
            "end_line": p_end,
            "names": [parent_def["name"]],
            "type": parent_def["type"],
            "class_name": parent_def.get("class_name"),
        })
    return res


def split_definition_recursive(
    d: dict[str, Any],
    all_definitions: list[dict[str, Any]],
    max_tokens: int,
    file_content: str | None,
) -> list[dict[str, Any]]:
    """
    Recursively split a definition into smaller segments.
    """
    d_start = d.get("start_line", 0)
    d_end = d.get("end_line", 0)

    children = []
    for other in all_definitions:
        s = other.get("start_line", 0)
        e = other.get("end_line", 0)
        if s >= d_start and e <= d_end and other is not d:
            children.append(other)

    children.sort(key=lambda x: x.get("start_line", 0))

    direct_children = []
    for c in children:
        is_nested = False
        for c2 in children:
            if c2 is c:
                continue
            if c2.get("start_line", 0) <= c.get("start_line", 0) and c2.get("end_line", 0) >= c.get("end_line", 0):
                if c2.get("end_line", 0) - c2.get("start_line", 0) > c.get("end_line", 0) - c.get("start_line", 0):
                    is_nested = True
                    break
                elif c2.get("end_line", 0) - c2.get("start_line", 0) == c.get("end_line", 0) - c.get("start_line", 0):
                    if children.index(c2) < children.index(c):
                        is_nested = True
                        break
        if not is_nested:
            direct_children.append(c)

    if direct_children:
        parent_lines = d["raw_text"].splitlines(keepends=True)
        segments = []
        current_line = d_start

        for c in direct_children:
            c_start = c["start_line"]
            c_end = c["end_line"]

            if c_start > current_line:
                gap_lines = parent_lines[current_line - d_start : c_start - d_start]
                gap_text = "".join(gap_lines)
                if gap_text.strip():
                    segments.extend(split_non_def_segment(gap_text, current_line, c_start - 1, d, max_tokens, file_content))

            segments.extend(split_definition_recursive(c, all_definitions, max_tokens, file_content))
            current_line = c_end + 1

        if d_end >= current_line:
            gap_lines = parent_lines[current_line - d_start : d_end - d_start + 1]
            gap_text = "".join(gap_lines)
            if gap_text.strip():
                segments.extend(split_non_def_segment(gap_text, current_line, d_end, d, max_tokens, file_content))

        return segments

    # No direct children definitions, try statement splitting
    language = d.get("language", "")
    if file_content and language:
        stmt_segs = get_statement_segments(
            file_path=d.get("file_path", ""),
            content=file_content,
            start_line=d_start,
            end_line=d_end,
            language=language,
            parent_name=d["name"],
            parent_type=d["type"],
        )
        if stmt_segs:
            res = []
            for seg in stmt_segs:
                if get_token_count(seg["text"]) <= max_tokens:
                    res.append({
                        "text": seg["text"],
                        "start_line": seg["start_line"],
                        "end_line": seg["end_line"],
                        "names": seg["names"],
                        "type": seg["type"],
                        "class_name": d.get("class_name"),
                    })
                else:
                    res.extend(split_non_def_segment(seg["text"], seg["start_line"], seg["end_line"], d, max_tokens, file_content))
            return res

    pieces = split_with_overlap(d["raw_text"], max_tokens=max_tokens)
    res = []
    lines_in_piece = max(1, (d_end - d_start + 1) // len(pieces))
    for idx, piece in enumerate(pieces):
        p_start = d_start + idx * lines_in_piece
        p_end = min(d_end, p_start + lines_in_piece - 1) if idx < len(pieces) - 1 else d_end
        res.append({
            "text": piece,
            "start_line": p_start,
            "end_line": p_end,
            "names": [d["name"]],
            "type": d["type"],
            "class_name": d.get("class_name"),
        })
    return res


def create_chunk_from_pack(pack: list[dict[str, Any]], file_key: tuple[str, str, str, str]) -> Chunk:
    """
    Combine multiple packed segments into a single Chunk.
    """
    file_path, display_path, normalized_path, language = file_key

    joined_text = "\n".join(seg["text"] for seg in pack)

    names = []
    for seg in pack:
        for name in seg.get("names", []):
            if name and name not in names:
                names.append(name)

    joined_names = ", ".join(names)
    header = f"# File: {display_path} | Definitions: {joined_names}"
    full_text = f"{header}\n{joined_text}"

    masked_text = mask_secrets(full_text)
    fp = compute_fingerprint(normalized_path, joined_names, masked_text)

    start_line = min(seg["start_line"] for seg in pack)
    end_line = max(seg["end_line"] for seg in pack)

    if len(pack) == 1:
        chunk_type = pack[0].get("type", "function")
    else:
        chunk_type = "packed"

    metadata = {
        "file_path": file_path,
        "display_path": display_path,
        "normalized_path": normalized_path,
        "function_name": joined_names,
        "start_line": start_line,
        "end_line": end_line,
        "type": chunk_type,
        "language": language,
        "fingerprint": fp,
        "class_name": pack[0].get("class_name") if len(pack) == 1 else None,
        "definition_names": names,
    }

    token_count = get_token_count(masked_text)

    return Chunk(text=masked_text, metadata=metadata, token_count=token_count)


def chunk_definitions(definitions: list[dict[str, Any]], max_tokens: int | None = None) -> list[Chunk]:
    """
    AST-aware chunking: Groups small adjacent definitions into one chunk up to max_tokens,
    and splits oversized definitions at child AST / statement boundaries.
    """
    if max_tokens is None:
        max_tokens = settings.CHUNK_MAX_TOKENS

    valid_defs = []
    for d in definitions:
        name = d.get("name")
        dtype = d.get("type")
        raw_text = d.get("raw_text")
        if not raw_text or not raw_text.strip():
            logger.warning("unparseable_or_empty_definition", name=name, type=dtype)
            continue
        valid_defs.append(d)

    from collections import defaultdict
    files_groups = defaultdict(list)
    for d in valid_defs:
        fpath = d.get("file_path") or ""
        dpath = d.get("display_path") or ""
        npath = d.get("normalized_path") or ""
        lang = d.get("language") or ""
        files_groups[(fpath, dpath, npath, lang)].append(d)

    all_chunks = []
    for (fpath, dpath, npath, lang), file_defs in files_groups.items():
        content = None
        if fpath:
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        file_defs.sort(key=lambda x: x.get("start_line", 0))

        top_levels = []
        for d in file_defs:
            is_child = False
            for other in file_defs:
                if other is d:
                    continue
                if (other.get("start_line", 0) <= d.get("start_line", 0) and
                    other.get("end_line", 0) >= d.get("end_line", 0)):
                    if other.get("end_line", 0) - other.get("start_line", 0) > d.get("end_line", 0) - d.get("start_line", 0):
                        is_child = True
                        break
                    elif other.get("end_line", 0) - other.get("start_line", 0) == d.get("end_line", 0) - d.get("start_line", 0):
                        if file_defs.index(other) < file_defs.index(d):
                            is_child = True
                            break
            if not is_child:
                top_levels.append(d)

        segments = []
        for tl in top_levels:
            tl["file_path"] = tl.get("file_path") or fpath
            tl["display_path"] = tl.get("display_path") or dpath
            tl["normalized_path"] = tl.get("normalized_path") or npath
            tl["language"] = tl.get("language") or lang

            segments.extend(split_definition_recursive(tl, file_defs, max_tokens, content))

        packed_chunks = []
        current_pack = []
        current_tokens = 0

        file_key = (fpath, dpath, npath, lang)

        for seg in segments:
            seg_text = seg["text"]
            seg_tokens = get_token_count(seg_text)

            if current_pack and current_tokens + seg_tokens > max_tokens:
                packed_chunks.append(create_chunk_from_pack(current_pack, file_key))
                current_pack = [seg]
                current_tokens = seg_tokens
            else:
                current_pack.append(seg)
                current_tokens += seg_tokens

        if current_pack:
            packed_chunks.append(create_chunk_from_pack(current_pack, file_key))

        all_chunks.extend(packed_chunks)

    return all_chunks
