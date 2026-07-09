# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/ingestion/file_filter.py
-----------------------------
Walk a cloned repository's working tree and produce a filtered, classified,
safely-decoded list of files worth indexing.

Responsibility boundary
-----------------------
This module receives a local clone path from Module 3 and returns a list of
:class:`FileRecord` objects ready for Module 5's parser.  It does NOT:
  - clone anything (Module 3),
  - parse/chunk/embed anything (Module 5+),
  - write to any store.

Tunable constants
-----------------
Constants are defined at module level (not scattered as magic numbers) so they
are easy to find, easy to test, and obvious to future readers.

safe_decode contract
--------------------
:func:`safe_decode` is the canonical UTF-8 decode function for this project.
Module 9's ``read_file`` agent tool imports it directly — there must never be
a second implementation.  Keep its signature stable.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.config import settings
from app.observability.logging_config import logger

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

# Hard size cap — files larger than this are skipped before reading content.
MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024       # 1 MB

# How many bytes to read when sniffing for null bytes (binary detection).
# Intentionally cheap/imperfect — see _is_binary() docstring.
BINARY_SNIFF_BYTES: int = 8_192                  # 8 KB

# Mean-line-length threshold for generated/minified file heuristic.
# Applied ONLY to files that already pass extension filtering — never used alone
# to avoid false-positiving on long but legitimate files (SQL fixtures, etc.).
MAX_MEAN_LINE_LENGTH: int = 300                  # characters per line

# Replacement-character ratio above which a file is considered corrupted.
# \ufffd is the Unicode replacement character inserted by errors='replace'.
# A 5% threshold catches accidentally-binary files with a code extension while
# tolerating occasional stray non-UTF-8 bytes in otherwise clean source.
MAX_REPLACEMENT_CHAR_RATIO: float = 0.05         # 5 %

# ---------------------------------------------------------------------------
# Exclusion rules — directories
# ---------------------------------------------------------------------------

EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",         # also caught by generated-path pattern (nested dist/ dirs)
    "build",
})

# ---------------------------------------------------------------------------
# Exclusion rules — file-level (hard rules, no exceptions)
# ---------------------------------------------------------------------------

# *.d.ts files are ALWAYS excluded.
#
# Rationale: TypeScript declaration files are almost always machine-generated
# (by `tsc --declaration`, `dts-gen`, or bundlers such as Rollup/Webpack) or
# are pure type-signature noise vendored from DefinitelyTyped.  Inconsistent
# partial inclusion — keeping some `.d.ts` files, silently dropping others —
# produces worse downstream indexing results than a clean, unconditional cut.
# Module 5's parser would process them as TypeScript, but the content adds no
# semantic signal that is not already present in the source `.ts` files.
_D_TS_SUFFIX = ".d.ts"

# *.lock files — always excluded.
# Package-manager lock files (package-lock.json, yarn.lock, Pipfile.lock, …)
# are generated, extremely long, and contain zero semantic signal for code
# understanding queries.
EXCLUDED_LOCK_SUFFIX: str = ".lock"

# ---------------------------------------------------------------------------
# Supported languages — v1 scope
# Out of scope: Go, Rust, C++, and all other compiled/binary languages.
# ---------------------------------------------------------------------------

#: Maps file extension → canonical language name used by Module 5's parser.
#: .jsx and .tsx are deliberately mapped to their base-language parser
#: (javascript / typescript) because tree-sitter uses the same grammar.
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py":  "python",
    ".js":  "javascript",
    ".jsx": "javascript",   # JSX   javascript parser (same tree-sitter grammar)
    ".ts":  "typescript",
    ".tsx": "tsx",          # TSX   specific tree-sitter grammar
}

# ---------------------------------------------------------------------------
# Generated-code path patterns (hard exclusions, pattern-based)
# ---------------------------------------------------------------------------

# These are treated as hard exclusions, not soft heuristics.
# Matched against the file's POSIX-style path relative to the repo root.
_GENERATED_PATH_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(^|/)dist/"),           # dist/ at any nesting level
    re.compile(r"(^|/)generated/"),      # generated/ at any nesting level
    re.compile(r"\.min\.js$"),           # minified JavaScript (by name)
    re.compile(r"_pb2\.py$"),            # protobuf-generated Python
    re.compile(r"_pb2_grpc\.py$"),       # protobuf gRPC-generated Python
)

# ---------------------------------------------------------------------------
# Output dataclass — the Module 5 handoff contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileRecord:
    """
    A single source file that survived all filtering.

    Fields
    ------
    path            Absolute path as a string.  Used to read the file content.
    display_path    Original casing, relative to the repo root.  Used in
                    UI output, citations, and agent answers.
    normalized_path Lowercased relative path.  Used for hashing, dedup, and
                    all internal indexing keys.  See path-normalization note.
    language        One of: ``python``, ``javascript``, ``typescript``.
                    Module 5 uses this field to select the tree-sitter parser.
    size_bytes      Working-tree file size in bytes.

    Path-normalization note
    -----------------------
    Keeping ``display_path`` and ``normalized_path`` separate guards against a
    real failure mode: a repo with both ``src/Auth.ts`` and ``src/auth.ts`` as
    distinct files on a case-sensitive (Linux) filesystem might be processed on
    a case-insensitive (macOS/Windows) filesystem.  Without this split the two
    entries could silently collide.  Both files survive as distinct records;
    ``normalized_path`` is consistent regardless of the host OS.
    """
    path: str             # absolute, for file I/O
    display_path: str     # original casing, relative, for user-facing output
    normalized_path: str  # lowercase, relative, for hashing and dedup
    language: str         # python | javascript | typescript
    size_bytes: int


# ---------------------------------------------------------------------------
# Public API — safe_decode
# ---------------------------------------------------------------------------

def safe_decode(path: Path) -> tuple[str | None, str | None]:
    """
    Read *path* and decode it as UTF-8, replacing undecodable bytes with \\ufffd.

    Returns
    -------
    ``(text, None)``
        Success — ``text`` is the decoded file content.
    ``(None, reason)``
        Failure — ``reason`` is a short human-readable explanation.
        The caller should log ``reason`` and skip the file.

    Corruption detection
    --------------------
    If the ratio of replacement characters (``\\ufffd``) in the decoded text
    exceeds :data:`MAX_REPLACEMENT_CHAR_RATIO` (5%), the file is considered
    corrupted or effectively binary and ``(None, reason)`` is returned.

    This is intentionally cheap — it is *not* a full binary classifier.
    The goal is to catch files that have a source-code extension (e.g. ``.py``)
    but are actually binary blobs or corrupted data that would produce garbage
    embeddings.  The null-byte sniff in :func:`_is_binary` provides an earlier,
    cheaper first pass; ``safe_decode`` provides a second layer.

    Reuse contract
    --------------
    This function is the **canonical** safe-decode implementation for this project.
    Module 9's ``read_file`` agent tool imports and calls it directly.
    **Do not** write a second decode implementation in Module 9 or anywhere else.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"read error: {exc}"

    if not raw:
        return "", None   # empty file is valid

    text = raw.decode("utf-8", errors="replace")

    replacement_count = text.count("\ufffd")
    ratio = replacement_count / len(text)
    if ratio > MAX_REPLACEMENT_CHAR_RATIO:
        return None, (
            f"replacement-char ratio {ratio:.1%} exceeds "
            f"{MAX_REPLACEMENT_CHAR_RATIO:.0%} threshold — likely binary or corrupted"
        )

    return text, None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _walk_files(root: Path) -> Iterator[Path]:
    """
    Yield all file paths under *root*, pruning :data:`EXCLUDED_DIRS` early.

    Using ``os.walk`` with in-place ``dirnames`` mutation is more efficient
    than ``Path.rglob('*')`` for large repos because excluded subtrees are
    never descended into — e.g. a 200 MB ``node_modules/`` directory is
    skipped with a single directory-name comparison, not by listing its
    100,000+ files only to discard them.
    """
    logger.debug("walk_files_started", root=str(root))
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
        # Prune in-place — prevents os.walk from descending into excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for filename in filenames:
            yield Path(dirpath) / filename


def _is_binary(path: Path) -> bool:
    """
    Return ``True`` if *path* appears to be a binary file.

    Algorithm: check for known binary magic bytes, then read the first 
    :data:`BINARY_SNIFF_BYTES` (8 KB) and check for null bytes (``\\x00``).

    Intentionally cheap/imperfect
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    This is *not* a full binary classifier.  Files that use null bytes as
    legitimate padding (e.g. UTF-16 encoded source files) will be incorrectly
    excluded; files that are mostly binary but happen to start with printable
    bytes may slip through.  The latter case is caught as a second defence by
    the replacement-character ratio check in :func:`safe_decode`.

    An unreadable file (``OSError``) is treated as binary to fail safely.
    """
    try:
        chunk = path.read_bytes()[:BINARY_SNIFF_BYTES]
        if not chunk:
            return False
            
        magic_signatures = (
            b"\x89PNG\x0d\x0a\x1a\x0a", # PNG
            b"\xff\xd8\xff",             # JPEG
            b"%PDF-",                    # PDF
            b"PK\x03\x04",               # ZIP/JAR
            b"\x7fELF",                  # ELF executable
            b"\xfe\xed\xfa\xce",         # Mach-O
            b"\xfe\xed\xfa\xcf",         # Mach-O
            b"\xce\xfa\xed\xfe",         # Mach-O
            b"\xcf\xfa\xed\xfe",         # Mach-O
            b"\x00\x00\x01\x00",         # ICO
            b"SQLite format 3\x00",      # SQLite
        )
        if chunk.startswith(magic_signatures):
            logger.debug("binary_file_detected_magic", path=str(path))
            return True

        if b"\x00" in chunk:
            logger.debug("binary_file_detected_nullbyte", path=str(path))
            return True
            
        return False
    except OSError as exc:
        logger.warning("file_read_error_treating_as_binary", path=str(path), error=str(exc))
        return True


def _is_generated_path(rel_posix: str) -> bool:
    """Return ``True`` if *rel_posix* matches any generated-code path pattern."""
    is_gen = any(pat.search(rel_posix) for pat in _GENERATED_PATH_PATTERNS)
    if is_gen:
        logger.debug("generated_path_detected", path=rel_posix)
    return is_gen


def _mean_line_length(text: str) -> float:
    """Return mean characters-per-line for *text*, or 0 for empty text."""
    if not text:
        return 0.0
    lines = text.splitlines()
    mean_len = len(text) / max(len(lines), 1)
    logger.debug("mean_line_length_calculated", mean_length=mean_len)
    return mean_len


# ---------------------------------------------------------------------------
# Public API — main filter function
# ---------------------------------------------------------------------------

def filter_repo_files(
    clone_path: Path,
    repo_id: str,
    commit_hash: str | None = None,
) -> list[FileRecord]:
    """
    Walk the working tree at *clone_path* and return all files worth parsing.

    Every file passes through the following pipeline in order:

    1. Hard directory exclusions (pruned by :func:`_walk_files`).
    2. Hard file-level exclusions (``.d.ts``, ``.lock``).
    3. Unsupported extension filter (v1: ``.py / .js / .jsx / .ts / .tsx``).
    4. Size cap (> :data:`MAX_FILE_SIZE_BYTES` → excluded).
    5. Binary sniff (null bytes in first 8 KB → excluded).
    6. Generated-code path patterns (``dist/``, ``*.min.js``, etc.).
    7. Content read: mean-line-length heuristic + encoding-corruption check.

    The exclusion breakdown is emitted as a single structured log line at the
    end, answering "why did my repo only index N files" from ``docker compose logs``
    alone.

    Parameters
    ----------
    clone_path:
        Absolute path to the cloned repo's working tree (from Module 3).
    repo_id:
        Used for log binding (from Module 3's :func:`~app.ingestion.clone.repo_id_for`).
    commit_hash:
        Optional; included in logs for traceability.

    Returns
    -------
    list[FileRecord]
        May be empty if the repo has no supported files (Python/JS/TS only in v1).
        Callers must handle the empty case; Module 12 surfaces a user-facing warning.
    """
    log = logger.bind(repo_id=repo_id, commit_hash=commit_hash or "unknown")
    log.info("file_filter_started", clone_path=str(clone_path))

    # Exclusion counters — reported as a single log line at the end
    n_binary = 0
    n_oversized = 0
    n_unsupported_ext = 0
    n_generated = 0
    n_corrupted = 0
    n_total = 0

    results: list[FileRecord] = []

    for abs_path in _walk_files(clone_path):
        if not abs_path.is_file():
            continue
        n_total += 1

        # Relative path (POSIX separators for cross-platform pattern matching)
        try:
            rel = abs_path.relative_to(clone_path)
        except ValueError:
            continue  # symlink outside the tree — skip safely
        rel_posix = rel.as_posix()

        # ── 1. Hard file-level exclusions ────────────────────────────────────
        name_lower = abs_path.name.lower()

        # .d.ts — unconditional cut (see module docstring rationale)
        if name_lower.endswith(_D_TS_SUFFIX):
            n_unsupported_ext += 1
            continue

        # .lock files — unconditional cut
        if name_lower.endswith(EXCLUDED_LOCK_SUFFIX):
            n_unsupported_ext += 1
            continue

        # ── 2. Supported extension ───────────────────────────────────────────
        # Use the lowercased suffix so Foo.PY is treated as .py
        suffix = ("." + name_lower.rsplit(".", 1)[-1]) if "." in name_lower else ""
        language = EXTENSION_TO_LANGUAGE.get(suffix)
        if language is None:
            n_unsupported_ext += 1
            continue

        # ── 3. Size cap ──────────────────────────────────────────────────────
        try:
            size_bytes = abs_path.stat().st_size
        except OSError:
            n_binary += 1   # unreadable — treat as binary/unavailable
            continue

        if size_bytes > MAX_FILE_SIZE_BYTES:
            n_oversized += 1
            continue

        # ── 4. Binary sniff ──────────────────────────────────────────────────
        if _is_binary(abs_path):
            n_binary += 1
            continue

        # ── 5. Generated-code path patterns ─────────────────────────────────
        if _is_generated_path(rel_posix):
            n_generated += 1
            continue

        # ── 6. Content: encoding safety + mean-line-length heuristic ─────────
        text, error = safe_decode(abs_path)
        if error is not None:
            log.info(
                "file_encoding_corrupted",
                path=rel_posix,
                reason=error,
            )
            n_corrupted += 1
            continue

        # Mean line length — only applied to JavaScript/TypeScript to avoid
        # false-positiving on long but legitimate files (SQL fixtures in Python).
        if text and language in ("javascript", "typescript") and _mean_line_length(text) > MAX_MEAN_LINE_LENGTH:
            n_generated += 1
            continue

        # ── 7. Build FileRecord ──────────────────────────────────────────────
        display_path = rel_posix                  # original casing
        normalized_path = rel_posix.lower()        # lowercased for dedup/hashing

        results.append(FileRecord(
            path=str(abs_path),
            display_path=display_path,
            normalized_path=normalized_path,
            language=language,
            size_bytes=size_bytes,
        ))

    # ── Emit single breakdown log line ────────────────────────────────────────
    log.info(
        "file_filter_completed",
        total_walked=n_total,
        excluded_binary=n_binary,
        excluded_oversized=n_oversized,
        excluded_unsupported_ext=n_unsupported_ext,
        excluded_generated=n_generated,
        excluded_corrupted=n_corrupted,
        files_surviving=len(results),
    )

    if not results:
        log.warning(
            "no_supported_files_found",
            hint="Only Python/JS/TS files are indexed in v1. "
                 "If this repo uses other languages, they are intentionally excluded.",
        )

    return results
