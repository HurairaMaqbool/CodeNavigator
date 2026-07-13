# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/retrieval/entity_retrieval.py
---------------------------------
Deterministic entity-level chunk expansion for class/function questions.

When a query targets a named entity (e.g. HTTPAdapter, Session), merge ALL indexed
chunks for that symbol instead of relying on similarity top-k alone.
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.symbol_lookup import list_symbol_chunk_records


_ENTITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:what does|what is|what are)\s+(?:the\s+)?([A-Z][A-Za-z0-9_]+)\b",
        re.I,
    ),
    re.compile(r"\b(?:responsibility|role|purpose) of\s+(?:the\s+)?([A-Z][A-Za-z0-9_]+)\b", re.I),
    re.compile(r"`([A-Z][A-Za-z0-9_.]+)`"),
    re.compile(r"\b([A-Z][A-Za-z0-9_]+)\s+(?:class|do|handle)\b"),
)


def extract_target_entity(question: str) -> str | None:
    """Return PascalCase entity name from a factual/mechanical class query."""
    q = question.strip()
    for pat in _ENTITY_PATTERNS:
        m = pat.search(q)
        if m:
            sym = m.group(1).split(".")[-1]
            if sym and sym[0].isupper() and len(sym) > 2:
                return sym
    return None


def entity_expansion_needed(question: str) -> bool:
    """True when the question asks about a named class/module responsibility."""
    q = question.lower()
    entity = extract_target_entity(question)
    if not entity:
        return False
    markers = (
        "what does", "what is", "what are", "responsibility", "role of",
        "purpose of", "do?", "do ",
    )
    return any(m in q for m in markers)


def _chunk_key(meta: dict[str, Any]) -> tuple[str, int, int]:
    path = str(meta.get("display_path") or meta.get("file_path") or "").lower()
    return (
        path,
        int(meta.get("start_line") or 0),
        int(meta.get("end_line") or 0),
    )


def expand_entity_hits(
    repo_id: str,
    question: str,
    hits: list[dict[str, Any]],
    *,
    max_entity_chunks: int = 12,
) -> list[dict[str, Any]]:
    """
    Prepend all BM25 chunks belonging to the target entity, deduped and capped.
    """
    entity = extract_target_entity(question)
    if not entity:
        return hits

    records = list_symbol_chunk_records(repo_id, entity)
    if not records:
        return hits

    seen: set[tuple[str, int, int]] = set()
    expanded: list[dict[str, Any]] = []

    def _append(rec: dict[str, Any], score: float) -> None:
        meta = dict(rec.get("metadata") or {})
        key = _chunk_key(meta)
        if not key[0] or key in seen:
            return
        seen.add(key)
        expanded.append({
            "chunk": rec.get("document") or "",
            "chunk_metadata": meta,
            "score": score,
        })

    for rec in records[:max_entity_chunks]:
        _append(rec, 0.93)

    for hit in hits:
        meta = hit.get("chunk_metadata") or {}
        key = _chunk_key(meta)
        if key in seen:
            continue
        if key[0]:
            seen.add(key)
        expanded.append(hit)

    return expanded


def expand_architecture_hits(
    repo_id: str,
    question: str,
    hits: list[dict[str, Any]],
    *,
    max_per_entity: int = 8,
) -> list[dict[str, Any]]:
    """Merge indexed chunks for architecture/extension-point queries."""
    from app.agent.prompts.answer_quality_dataset import classify_query

    if classify_query(question) != "ARCHITECTURE":
        return hits

    q = question.lower()
    symbols: list[str] = []
    if any(w in q for w in ("transport", "adapter", "retry", "mount", "subclass", "custom")):
        symbols.extend(["BaseAdapter", "HTTPAdapter", "Session"])

    merged = hits
    for sym in dict.fromkeys(symbols):
        merged = expand_entity_hits(
            repo_id,
            f"What does {sym} do?",
            merged,
            max_entity_chunks=max_per_entity,
        )
    return merged


def log_retrieval_snapshot(
    repo_id: str,
    question: str,
    chunks: list[dict[str, Any]],
    *,
    phase: str = "post_act",
) -> None:
    """Structured retrieval audit for consistency debugging."""
    from app.observability.logging_config import logger

    top = []
    for hit in (chunks or [])[:8]:
        meta = hit.get("chunk_metadata") or {}
        top.append({
            "path": meta.get("display_path") or meta.get("file_path"),
            "lines": f"{meta.get('start_line')}-{meta.get('end_line')}",
            "fn": meta.get("function_name"),
            "score": round(float(hit.get("score", 0.0)), 4),
        })
    logger.info(
        "retrieval_snapshot",
        phase=phase,
        repo_id=repo_id,
        question=question[:120],
        chunk_count=len(chunks or []),
        top_chunks=top,
    )
