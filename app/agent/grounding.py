# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/grounding.py
----------------------
Layer 2 — Structured FINALIZE output contract.

FINALIZE returns a JSON list of {claim, citation} objects. This module parses
that payload and renders readable markdown with inline citations for the API/UI.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.observability.logging_config import logger

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_ABSTENTION_MARKERS = (
    "insufficient",
    "could not confirm",
    "cannot confirm",
    "not enough evidence",
    "not fully answer",
    "does not include",
    "do not include",
    "could not find",
    "cannot find",
    "not in the provided",
    "not in the context",
    "available chunks",
    "from the available",
)


def strip_json_fences(raw: str) -> str:
    text = (raw or "").strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    return text


def parse_finalize_json(raw: str) -> list[dict[str, Any]]:
    """
    Parse FINALIZE structured output into a list of claim dicts.

    Accepts ``{"claims": [...]}`` or a bare JSON array.
    Returns an empty list on parse failure (caller may fall back to prose).
    """
    clean = strip_json_fences(raw)
    if not clean:
        return []

    try:
        payload = json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.warning("finalize_json_parse_failed", error=str(exc), preview=clean[:200])
        return []

    if isinstance(payload, dict):
        claims = payload.get("claims")
        if isinstance(claims, list):
            return _normalize_claim_list(claims)
        return []

    if isinstance(payload, list):
        return _normalize_claim_list(payload)

    return []


def _normalize_claim_list(items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        claim_text = str(item.get("claim") or item.get("text") or "").strip()
        if not claim_text:
            continue
        citation = _normalize_citation(item.get("citation"))
        out.append({"claim": claim_text, "citation": citation})
    return out


def _normalize_citation(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    path = str(raw.get("file_path") or raw.get("path") or "").strip()
    if not path:
        return None
    start = raw.get("start_line")
    end = raw.get("end_line")
    try:
        start_i = int(start) if start is not None else None
    except (TypeError, ValueError):
        start_i = None
    try:
        end_i = int(end) if end is not None else start_i
    except (TypeError, ValueError):
        end_i = start_i
    if start_i is None:
        return None
    if end_i is None:
        end_i = start_i
    return {
        "file_path": path.replace("\\", "/").lstrip("/"),
        "start_line": start_i,
        "end_line": end_i,
    }


def is_abstention_claim(claim: dict[str, Any]) -> bool:
    """True when the claim explicitly acknowledges missing/insufficient context."""
    text = str(claim.get("claim") or "").lower()
    if claim.get("citation") is not None:
        return False
    return any(marker in text for marker in _ABSTENTION_MARKERS)


def is_factual_claim(claim: dict[str, Any]) -> bool:
    """Factual claims require a citation; abstention/meta claims do not."""
    return claim.get("citation") is not None and not is_abstention_claim(claim)


def format_inline_citation(citation: dict[str, Any]) -> str:
    path = citation["file_path"]
    start = int(citation["start_line"])
    end = int(citation.get("end_line") or start)
    if end != start:
        return f"`{path}:{start}-{end}`"
    return f"`{path}:{start}`"


def render_claims_markdown(claims: list[dict[str, Any]]) -> str:
    """Render structured claims into markdown prose with inline citations."""
    if not claims:
        return ""

    paragraphs: list[str] = []
    for item in claims:
        text = str(item.get("claim") or "").strip()
        citation = item.get("citation")
        if citation and is_factual_claim(item):
            paragraphs.append(f"{text} {format_inline_citation(citation)}")
        else:
            paragraphs.append(text)

    return "\n\n".join(paragraphs)


def claims_to_sources(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build API source rows from structured claims (deduped by file+lines)."""
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in claims:
        citation = item.get("citation")
        if not citation:
            continue
        path = citation["file_path"]
        start = int(citation["start_line"])
        end = int(citation.get("end_line") or start)
        lines = f"{start}-{end}" if end != start else str(start)
        sig = f"{path}::{lines}"
        if sig in seen:
            continue
        seen.add(sig)
        sources.append({
            "file_path": path,
            "function_name": None,
            "lines": lines,
            "start_line": start,
            "end_line": end,
        })
    return sources
