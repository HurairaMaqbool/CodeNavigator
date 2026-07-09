# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/symbol_lookup.py
--------------------------
Resolve symbols to authoritative file paths and line numbers using BM25
metadata and on-disk source files. Used by citation repair so answers cite
class/function definitions, not arbitrary chunks that mention a name.
"""
from __future__ import annotations

import pickle
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings

_CLASS_DEF = re.compile(r"^class\s+({name})\b", re.MULTILINE)
_FUNC_DEF = re.compile(r"^def\s+({name})\b", re.MULTILINE)


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./").lower()


def _clone_root(repo_id: str) -> Path:
    return Path(settings.REPOS_PATH) / repo_id / "clone"


@lru_cache(maxsize=32)
def _load_records(repo_id: str) -> tuple[dict[str, Any], ...]:
    from app.retrieval.bm25_store import _index_path_for

    pkl = _index_path_for(repo_id)
    if not pkl.exists():
        return ()
    with pkl.open("rb") as f:
        _bm25, records = pickle.load(f)
    return tuple(records)


@lru_cache(maxsize=256)
def _scan_definition_line(repo_id: str, rel_path: str, symbol: str, kind: str) -> int | None:
    """Return 1-based line number of class/def definition in source, if found."""
    root = _clone_root(repo_id)
    clean = rel_path.replace("\\", "/").lstrip("./")
    abs_path = root / clean
    if not abs_path.is_file():
        return None
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if kind == "class":
        m = re.search(rf"^class\s+{re.escape(symbol)}\b", text, re.MULTILINE)
    else:
        m = re.search(rf"^def\s+{re.escape(symbol)}\b", text, re.MULTILINE)
    if not m:
        return None
    return text[: m.start()].count("\n") + 1


def _paths_for_symbol(repo_id: str, symbol: str) -> list[dict[str, Any]]:
    """BM25 metadata rows that define or belong to symbol."""
    sym = symbol.split(".")[-1]
    sym_lower = sym.lower()
    matches: list[dict[str, Any]] = []
    for rec in _load_records(repo_id):
        meta = rec.get("metadata") or {}
        fn = meta.get("function_name") or ""
        doc = rec.get("document") or ""
        base = fn.split(".")[-1] if fn else ""
        if fn == sym or base == sym:
            matches.append(meta)
            continue
        if fn.startswith(f"{sym}.") or fn == f"{sym}":
            matches.append(meta)
            continue
        if f"Class: {sym}." in doc or f"Class: {sym}\n" in doc:
            matches.append(meta)
            continue
        if f"class {sym}" in doc and sym[0].isupper():
            matches.append(meta)
            continue
        if fn.lower() == sym_lower and sym_lower != sym:
            matches.append(meta)
    return matches


def resolve_symbol_location(
    repo_id: str,
    symbol: str,
    *,
    prefer_path: str | None = None,
    kind: str = "class",
) -> dict[str, Any] | None:
    """
    Return {file_path, start_line, end_line, function_name} for a symbol.
    Prefers on-disk class/def line, then earliest BM25 chunk for that symbol.
    """
    sym = symbol.split(".")[-1]
    metas = _paths_for_symbol(repo_id, sym)
    if prefer_path:
        pref = _norm_path(prefer_path)
        metas = [m for m in metas if _norm_path(m.get("display_path") or m.get("file_path") or "") == pref] or metas

    # Prefer src/ over tests/
    def _sort_key(m: dict[str, Any]) -> tuple[int, int, str]:
        path = (m.get("display_path") or m.get("file_path") or "").lower()
        src_penalty = 0 if "/src/" in path or path.startswith("src/") else 1
        test_penalty = 1 if "/tests/" in path or path.startswith("tests/") else 0
        start = m.get("start_line") or 99999
        return (test_penalty, src_penalty, start)

    metas = sorted(metas, key=_sort_key)
    if not metas:
        return None

    # Try source scan on best candidate paths
    seen_paths: set[str] = set()
    for meta in metas:
        path = meta.get("display_path") or meta.get("file_path") or ""
        if not path or _norm_path(path) in seen_paths:
            continue
        seen_paths.add(_norm_path(path))
        def_line = _scan_definition_line(repo_id, path, sym, kind)
        if def_line is not None:
            end = meta.get("end_line") or def_line
            return {
                "file_path": path,
                "function_name": sym if kind == "class" else meta.get("function_name"),
                "start_line": def_line,
                "end_line": end if end >= def_line else def_line,
            }

    best = metas[0]
    path = best.get("display_path") or best.get("file_path") or ""
    start = best.get("start_line")
    end = best.get("end_line") or start
    if not path or start is None:
        return None
    return {
        "file_path": path,
        "function_name": best.get("function_name") or sym,
        "start_line": start,
        "end_line": end,
    }


def symbol_paths(repo_id: str, symbol: str) -> set[str]:
    """Normalized paths where symbol is defined."""
    return {
        _norm_path(m.get("display_path") or m.get("file_path") or "")
        for m in _paths_for_symbol(repo_id, symbol)
        if m.get("display_path") or m.get("file_path")
    }
