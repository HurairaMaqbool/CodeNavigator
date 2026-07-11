# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/ingestion/path_normalize.py
---------------------------------
Canonical repo-relative path normalization at ingestion boundary.

All downstream modules (BM25, vector store, graph, verification) must consume
paths produced here — never raw Windows backslashes or absolute clone paths.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

_BACKSLASH = re.compile(r"\\+")
_CLONE_MARKER = "/clone/"


def normalize_repo_path(path: str) -> str:
    """
    Canonical forward-slash repo-relative path (no leading slash).

    Strips clone-directory prefixes when present.
    """
    clean = _BACKSLASH.sub("/", (path or "").strip()).lstrip("/")
    idx = clean.find(_CLONE_MARKER)
    if idx != -1:
        clean = clean[idx + len(_CLONE_MARKER):]
    parts = clean.split("/")
    if len(parts) > 2 and parts[0] == "repos" and parts[2] == "clone":
        clean = "/".join(parts[3:])
    return str(PurePosixPath(clean))


def assert_normalized_path(path: str, *, context: str = "") -> str:
    """
    Validate path is canonical; log and fix minor issues, raise on backslashes.

    Call at ingestion write boundaries so bad paths fail fast.
    """
    if not path:
        raise ValueError(f"empty path{f' ({context})' if context else ''}")
    if "\\" in path:
        from app.observability.logging_config import logger

        logger.warning("path_normalize_backslash", path=path[:120], context=context)
    norm = normalize_repo_path(path)
    if norm != path.replace("\\", "/").lstrip("/"):
        from app.observability.logging_config import logger

        logger.debug("path_normalized", before=path[:120], after=norm, context=context)
    return norm
