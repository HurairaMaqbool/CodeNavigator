# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/retrieval_metrics.py
-------------------------
Shared retrieval scoring for eval and golden CI.
"""
from __future__ import annotations

from typing import Any


def paths_match(source_path: str, gt_file: str) -> bool:
    """Suffix-aware file match (src/requests/auth.py vs requests/auth.py)."""
    s = source_path.replace("\\", "/").lstrip("./").lower()
    g = gt_file.replace("\\", "/").lstrip("./").lower()
    if not s or not g:
        return False
    if s == g:
        return True
    return s.endswith("/" + g) or g.endswith("/" + s) or s.endswith(g) or g.endswith(s)


def collect_cited_files(res: dict[str, Any], *, top_k: int = 5) -> list[str]:
    """Unique file paths from sources, retrieval hits, and answer citations."""
    files: list[str] = []

    def add(fp: str) -> None:
        fp = (fp or "").strip()
        if fp and fp not in files:
            files.append(fp)

    for s in res.get("sources") or []:
        add(s.get("file_path", ""))

    for h in (res.get("retrieval_hits") or [])[:top_k]:
        meta = h.get("chunk_metadata") or h.get("metadata") or {}
        add(
            h.get("file_path")
            or meta.get("display_path")
            or meta.get("file_path")
            or ""
        )

    try:
        from app.agent.confidence import extract_file_path_mentions

        for p in extract_file_path_mentions(res.get("answer") or ""):
            add(p)
    except Exception:
        pass

    return files


def precision_at_k(
    res: dict[str, Any],
    ground_truth_files: list[str],
    *,
    k: int = 3,
) -> tuple[float, list[str], bool]:
    """
    Return (precision, top_k_files, any_hit).

    Uses sources first, then fills from retrieval_hits up to k files.
    """
    gt = ground_truth_files or []
    if not gt:
        return 0.0, [], False

    files = collect_cited_files(res, top_k=k)[:k]
    if not files:
        return 0.0, [], False

    hits = sum(1 for f in files if any(paths_match(f, g) for g in gt))
    any_hit = hits > 0
    return hits / len(files), files, any_hit
