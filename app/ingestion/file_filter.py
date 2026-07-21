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
This module receives a local clone path from Module 7 (clone.py) and returns
a list of FileRecord objects ready for the parser.  It does NOT:
  - clone anything (Module 7),
  - parse/chunk/embed anything (Module 9+),
  - write to any vector or graph store.

Tunable constants
-----------------
Constants are defined at module level so they are easy to find, easy to test,
and obvious to future readers.

safe_decode contract
--------------------
safe_decode is the canonical UTF-8 decode function for this project.
Module 9 read_file agent tool imports it directly.
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

MAX_FILE_SIZE_BYTES: int = settings.MAX_FILE_SIZE_BYTES
BINARY_SNIFF_BYTES: int = settings.BINARY_SNIFF_BYTES
MAX_MEAN_LINE_LENGTH: int = settings.MAX_MEAN_LINE_LENGTH
MAX_REPLACEMENT_CHAR_RATIO: float = settings.MAX_REPLACEMENT_CHAR_RATIO

# ---------------------------------------------------------------------------
# Exclusion rules -- directories (applied DURING walk, not after)
# ---------------------------------------------------------------------------

EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "target", "out", "data", ".next", "repos",
})

# ---------------------------------------------------------------------------
# Exclusion rules -- file-level
# ---------------------------------------------------------------------------

_D_TS_SUFFIX = ".d.ts"
EXCLUDED_LOCK_SUFFIX: str = ".lock"

from app.ingestion.language_registry import EXTENSION_TO_LANGUAGE
from app.ingestion.path_normalize import assert_normalized_path

# ---------------------------------------------------------------------------
# Generated-code path patterns
# ---------------------------------------------------------------------------

_GENERATED_PATH_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(^|/)dist/"),
    re.compile(r"(^|/)generated/"),
    re.compile(r"\.min\.js$"),
    re.compile(r"_pb2\.py$"),
    re.compile(r"_pb2_grpc\.py$"),
)

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileRecord:
    path: str             # absolute, for file I/O
    display_path: str     # original casing, relative, for user-facing output
    normalized_path: str  # lowercase, relative, for hashing and dedup
    language: str         # python | javascript | typescript | go | java | rust
    size_bytes: int


# ---------------------------------------------------------------------------
# Public API -- safe_decode
# ---------------------------------------------------------------------------

def safe_decode(path: Path) -> tuple[str | None, str | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"read error: {exc}"
    if not raw:
        return "", None
    text = raw.decode("utf-8", errors="replace")
    replacement_count = text.count("\ufffd")
    ratio = replacement_count / len(text)
    if ratio > MAX_REPLACEMENT_CHAR_RATIO:
        return None, (
            f"replacement-char ratio {ratio:.1%} exceeds "
            f"{MAX_REPLACEMENT_CHAR_RATIO:.0%} threshold -- likely binary or corrupted"
        )
    return text, None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _walk_files(root: Path) -> Iterator[Path]:
    logger.debug("walk_files_started", root=str(root))
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for filename in filenames:
            yield Path(dirpath) / filename


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:BINARY_SNIFF_BYTES]
        if not chunk:
            return False
        magic_signatures = (
            b"\x89PNG\x0d\x0a\x1a\x0a", b"\xff\xd8\xff", b"%PDF-",
            b"PK\x03\x04", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
            b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\x00\x00\x01\x00",
            b"SQLite format 3\x00",
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
    is_gen = any(pat.search(rel_posix) for pat in _GENERATED_PATH_PATTERNS)
    if is_gen:
        logger.debug("generated_path_detected", path=rel_posix)
    return is_gen


def _mean_line_length(text: str) -> float:
    if not text:
        return 0.0
    lines = text.splitlines()
    mean_len = len(text) / max(len(lines), 1)
    logger.debug("mean_line_length_calculated", mean_length=mean_len)
    return mean_len


# ---------------------------------------------------------------------------
# Public API -- main filter function
# ---------------------------------------------------------------------------

def filter_repo_files(
    clone_path: Path,
    repo_id: str,
    commit_hash: str | None = None,
) -> list[FileRecord]:
    # Always resolve to absolute so FileRecord.path is always absolute.
    clone_path = Path(clone_path).resolve()

    log = logger.bind(repo_id=repo_id, commit_hash=commit_hash or "unknown")
    log.info("file_filter_started", clone_path=str(clone_path))

    n_binary = n_oversized = n_unsupported_ext = n_generated = n_corrupted = n_total = 0
    results: list[FileRecord] = []

    for abs_path in _walk_files(clone_path):
        if not abs_path.is_file():
            continue
        n_total += 1

        try:
            rel = abs_path.relative_to(clone_path)
        except ValueError:
            continue
        rel_posix = rel.as_posix()

        name_lower = abs_path.name.lower()

        if name_lower.endswith(_D_TS_SUFFIX):
            n_unsupported_ext += 1
            continue
        if name_lower.endswith(EXCLUDED_LOCK_SUFFIX):
            n_unsupported_ext += 1
            continue

        suffix = ("." + name_lower.rsplit(".", 1)[-1]) if "." in name_lower else ""
        language = EXTENSION_TO_LANGUAGE.get(suffix)
        if language is None:
            # Check for exact filenames like Dockerfile, Makefile
            if name_lower in ("dockerfile", "makefile"):
                language = "dockerfile" if name_lower == "dockerfile" else "makefile"
            else:
                n_unsupported_ext += 1
                continue

        try:
            size_bytes = abs_path.stat().st_size
        except OSError:
            n_binary += 1
            continue

        if size_bytes > MAX_FILE_SIZE_BYTES:
            n_oversized += 1
            continue

        if _is_binary(abs_path):
            n_binary += 1
            continue

        if _is_generated_path(rel_posix):
            n_generated += 1
            continue

        text, error = safe_decode(abs_path)
        if error is not None:
            log.info("file_encoding_corrupted", path=rel_posix, reason=error)
            n_corrupted += 1
            continue

        if text and language in ("javascript", "typescript") and _mean_line_length(text) > MAX_MEAN_LINE_LENGTH:
            n_generated += 1
            continue

        display_path = assert_normalized_path(rel_posix, context="file_filter")
        normalized_path = display_path.lower()

        results.append(FileRecord(
            path=str(abs_path),
            display_path=display_path,
            normalized_path=normalized_path,
            language=language,
            size_bytes=size_bytes,
        ))

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

    # -- FILTERED checkpoint (Module #9 spec requirement) -----------------------
    try:
        from app.ingestion.metadata_store import metadata_store, Stage
        # mark_filtered sets the file_count for diagnostic info
        metadata_store.mark_filtered(repo_id, file_count=len(results))
        # Idempotent write using update() as required by Module #9 spec
        metadata_store.update(repo_id, Stage.FILTERING)
    except Exception as meta_exc:
        log.warning("failed_to_write_filtered_checkpoint", error=str(meta_exc))

    # -- Zero-files guard ---------------------------------------------------
    if not results:
        reason = (
            f"No supported source files found after filtering "
            f"(walked {n_total} files; supported extensions: "
            f"{', '.join(sorted(EXTENSION_TO_LANGUAGE))}). "
            f"Check that the repository contains Python/JS/TS/Go/Java/Rust source files "
            f"and is not entirely composed of generated, binary, or oversized files."
        )
        log.warning("no_supported_files_found", reason=reason)
        try:
            from app.ingestion.metadata_store import metadata_store, Stage
            metadata_store.update(repo_id, Stage.FAILED, error=reason)
        except Exception as meta_exc:
            log.warning("failed_to_mark_ingestion_failed", error=str(meta_exc))

    return results


# ---------------------------------------------------------------------------
# Public API -- is_minified (standalone helper)
# ---------------------------------------------------------------------------

def is_minified(file_path: str | Path) -> bool:
    p = Path(file_path)
    try:
        chunk = p.read_bytes()[:51_200]
        if not chunk:
            return False
        text = chunk.decode("utf-8", errors="replace")
        return _mean_line_length(text) > MAX_MEAN_LINE_LENGTH
    except OSError:
        return False
