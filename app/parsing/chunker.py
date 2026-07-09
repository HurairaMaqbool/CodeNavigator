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
from typing import Sequence

from app.observability.logging_config import logger
from app.config import settings
from app.parsing.tree_sitter_parser import ParsedClass, ParsedFile, ParsedFunction

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

#: A class body shorter than this (in source lines) is emitted as one chunk.
#: At or above this threshold its methods are chunked individually.
MAX_CLASS_LINES_BEFORE_SPLIT: int = 200

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


def _make_chunks(
    *,
    raw_body: str,
    header: str,
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
    1. Prepend synthetic header to raw body.
    2. Mask secrets on the full text (header + body).
    3. Split if over token limit.
    4. Compute fingerprint on each masked piece.
    """
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
    header = f"# File: {display_path} | Function: {func.name}"
    return _make_chunks(
        raw_body=body,
        header=header,
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
    header = f"# File: {display_path} | Class: {class_name}.{method.name}"
    return _make_chunks(
        raw_body=body,
        header=header,
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
    header = f"# File: {display_path} | Class: {cls.name}"
    return _make_chunks(
        raw_body=body,
        header=header,
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
