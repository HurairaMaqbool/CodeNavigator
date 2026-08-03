# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/security/path_jail.py
-------------------------
Resolve user-supplied paths safely inside a repository clone root.
"""
from __future__ import annotations

from pathlib import Path


class PathJailError(ValueError):
    """Raised when a path escapes the allowed root directory."""


def normalize_repo_relative_path(file_path: str) -> str:
    """Strip clone prefixes from LLM-supplied paths."""
    clean = file_path.replace("\\", "/")
    # Reject UNC paths explicitly
    if file_path.startswith("\\\\") or file_path.startswith("//"):
        raise PathJailError(f"UNC paths not allowed: {file_path!r}")
    clean = clean.lstrip("/")
    clone_marker = "/clone/"
    idx = clean.find(clone_marker)
    if idx != -1:
        clean = clean[idx + len(clone_marker):]
    else:
        parts = clean.split("/")
        if len(parts) > 2 and parts[0] == "repos" and parts[2] == "clone":
            clean = "/".join(parts[3:])
    return clean


def resolve_jailed_path(root: Path, relative_path: str) -> Path:
    """
    Return absolute path inside *root* or raise PathJailError.

    Uses resolve() + is_relative_to() to block ``../`` traversal.
    """
    try:
        root_resolved = root.resolve()
        clean = normalize_repo_relative_path(relative_path)
        candidate = (root_resolved / clean).resolve()
        if not candidate.is_relative_to(root_resolved):
            raise PathJailError(f"Path escapes repository root: {relative_path!r}")
        return candidate
    except PathJailError:
        raise
    except Exception as exc:
        raise PathJailError(f"Invalid path {relative_path!r}: {exc}") from exc
