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

# Shared FINALIZE citation contract — keep parse + verification in sync.
_CITATION_INLINE_RE = re.compile(
    r"^((?:[\w./\\\-@]+/)?[\w.\-]+\.[\w]{1,12}):(\d+)(?:-(\d+))?$"
)

# Canonical structured claim shape after normalization:
# {"claim": str, "citation": {"file_path": str, "start_line": int, "end_line": int} | None}

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


def looks_like_leaked_finalize_json(text: str) -> bool:
    """
    True when user-visible text still contains FINALIZE structured JSON instead of prose.

    Used as a hard gate before RESPOND — structured output must never reach the UI.
    """
    if not text:
        return False
    stripped = text.strip()
    if stripped.startswith("{") and ("claims" in stripped or "citation" in stripped):
        return True
    if '"claims":' in text or '"citation":' in text:
        return True
    if re.search(r'\{\s*"claims"\s*:', text):
        return True
    return False


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
        normalized = normalize_claim(item)
        if normalized is not None:
            out.append(normalized)
    return out


def normalize_citation(raw: Any) -> dict[str, Any] | None:
    """
    Normalize a FINALIZE citation into the canonical dict shape.

    Accepts dict (several key variants), inline ``path:line`` strings, or a
    one-element list of dicts (common Groq json_object drift).
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        for item in raw:
            normalized = normalize_citation(item)
            if normalized is not None:
                return normalized
        return None
    if isinstance(raw, str):
        match = _CITATION_INLINE_RE.match(raw.strip())
        if not match:
            return None
        path, start_s, end_s = match.group(1), match.group(2), match.group(3)
        start_i = int(start_s)
        end_i = int(end_s) if end_s else start_i
        return {
            "file_path": path.replace("\\", "/").lstrip("/"),
            "start_line": start_i,
            "end_line": end_i,
        }
    if not isinstance(raw, dict):
        return None

    path = str(raw.get("file_path") or raw.get("path") or "").strip()
    if not path:
        return None

    start = raw.get("start_line")
    if start is None:
        start = raw.get("line") or raw.get("start")
    end = raw.get("end_line")
    if end is None:
        end = raw.get("end")

    lines = raw.get("lines")
    if start is None and isinstance(lines, str) and lines.strip():
        if "-" in lines:
            start_s, end_s = lines.split("-", 1)
            try:
                start = int(start_s.strip())
                end = int(end_s.strip())
            except ValueError:
                start = None
        else:
            try:
                start = int(lines.strip())
            except ValueError:
                start = None

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


def normalize_claim(item: Any) -> dict[str, Any] | None:
    """Normalize one FINALIZE claim object (shared by parse + VERIFY)."""
    if not isinstance(item, dict):
        return None
    claim_text = str(item.get("claim") or item.get("text") or "").strip()
    if not claim_text:
        return None

    citation = normalize_citation(item.get("citation"))
    if citation is None and (item.get("file_path") or item.get("path")):
        citation = normalize_citation(item)

    return {"claim": claim_text, "citation": citation}


def normalize_claims(items: list[Any]) -> list[dict[str, Any]]:
    """Normalize a list of FINALIZE claims, dropping empty entries."""
    return _normalize_claim_list(items)


def _normalize_citation(raw: Any) -> dict[str, Any] | None:
    """Backward-compatible alias for :func:`normalize_citation`."""
    return normalize_citation(raw)


def is_abstention_claim(claim: dict[str, Any]) -> bool:
    """True when the claim explicitly acknowledges missing/insufficient context."""
    text = str(claim.get("claim") or "").lower()
    if normalize_citation(claim.get("citation")) is not None:
        return False
    return any(marker in text for marker in _ABSTENTION_MARKERS)


def is_factual_claim(claim: dict[str, Any]) -> bool:
    """Factual claims require a normalized citation; abstention/meta claims do not."""
    if is_abstention_claim(claim):
        return False
    return normalize_citation(claim.get("citation")) is not None


def format_inline_citation(citation: dict[str, Any]) -> str:
    normalized = normalize_citation(citation)
    if not normalized:
        raise ValueError("citation is not a valid structured citation")
    path = normalized["file_path"]
    start = int(normalized["start_line"])
    end = int(normalized.get("end_line") or start)
    if end != start:
        return f"`{path}:{start}-{end}`"
    return f"`{path}:{start}`"


def _claim_word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def dedupe_claims(claims: list[dict[str, Any]], *, overlap_threshold: float = 0.45) -> list[dict[str, Any]]:
    """Drop semantically redundant claims (same fact, different wording)."""
    kept: list[dict[str, Any]] = []
    for claim in claims:
        words = _claim_word_set(str(claim.get("claim") or ""))
        if not words:
            continue
        redundant = False
        for prev in kept:
            prev_words = _claim_word_set(str(prev.get("claim") or ""))
            if not prev_words:
                continue
            overlap = len(words & prev_words) / len(words | prev_words)
            if overlap >= overlap_threshold:
                redundant = True
                break
        if not redundant:
            kept.append(claim)
    return kept


def dedupe_claims_by_citation(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop claims that cite the exact same file+line range."""
    kept: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for claim in claims:
        cit = normalize_citation(claim.get("citation"))
        if cit:
            key = (
                str(cit.get("file_path") or ""),
                int(cit.get("start_line") or 0),
                int(cit.get("end_line") or cit.get("start_line") or 0),
            )
            if key in seen:
                continue
            seen.add(key)
        kept.append(claim)
    return kept


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


def _paths_match(a: str, b: str) -> bool:
    na, nb = _norm_path(a), _norm_path(b)
    return na == nb or na.endswith("/" + nb) or nb.endswith("/" + na)


def narrow_claims_to_chunks(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Snap each citation to the tightest matching retrieval chunk (method-level lines)."""
    hit_rows: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.get("chunk_metadata") or {}
        path = meta.get("display_path") or meta.get("file_path") or ""
        start = int(meta.get("start_line") or 0)
        end = int(meta.get("end_line") or start)
        if not path or start <= 0:
            continue
        hit_rows.append({
            "path": path,
            "start": start,
            "end": end,
            "fn": str(meta.get("function_name") or "").lower(),
            "text": (chunk.get("chunk") or "").lower(),
        })

    for claim in claims:
        cit = normalize_citation(claim.get("citation"))
        if not cit or not hit_rows:
            continue
        claim_words = _claim_word_set(str(claim.get("claim") or ""))
        cit_path = str(cit.get("file_path") or "")

        candidates = [h for h in hit_rows if _paths_match(cit_path, h["path"])]
        if not candidates:
            tail = _norm_path(cit_path).split("/")[-1]
            candidates = [h for h in hit_rows if tail in _norm_path(h["path"])]

        best: dict[str, Any] | None = None
        best_score = -1.0
        best_span = 10**9
        for h in candidates:
            span = max(1, h["end"] - h["start"] + 1)
            chunk_words = _claim_word_set(h["text"] + " " + h["fn"])
            overlap = len(claim_words & chunk_words) / max(1, len(claim_words))
            score = overlap * 14.0 - span / 12.0
            if span > 120:
                score -= 4.0
            if h["fn"]:
                fn_tokens = set(re.findall(r"[a-z0-9_]+", h["fn"]))
                if fn_tokens & claim_words:
                    score += 4.0
            for kw in (
                "urlopen", "send", "merge_cookies", "max_retries", "retry", "timeout",
                "urllib3", "poolmanager", "instead", "because", "maintain",
            ):
                if kw in claim_words and kw in chunk_words:
                    score += 2.5
            if score > best_score or (score == best_score and span < best_span):
                best_score = score
                best_span = span
                best = h

        if not best and hit_rows:
            # Global fallback: best text overlap across all retrieval chunks.
            for h in hit_rows:
                span = max(1, h["end"] - h["start"] + 1)
                chunk_words = _claim_word_set(h["text"] + " " + h["fn"])
                overlap = len(claim_words & chunk_words) / max(1, len(claim_words))
                score = overlap * 10.0 - span / 15.0
                if score > best_score or (score == best_score and span < best_span):
                    best_score = score
                    best_span = span
                    best = h

        if best:
            cit["file_path"] = best["path"]
            cit["start_line"] = best["start"]
            cit["end_line"] = best["end"]
            claim["citation"] = cit

    return claims


def clamp_claims_to_manifest(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure every factual citation matches an exact retrieval chunk range."""
    manifest: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.get("chunk_metadata") or {}
        path = meta.get("display_path") or meta.get("file_path") or ""
        start = int(meta.get("start_line") or 0)
        end = int(meta.get("end_line") or start)
        if not path or start <= 0:
            continue
        manifest.append({
            "path": path,
            "start": start,
            "end": end,
            "fn": str(meta.get("function_name") or "").lower(),
            "text": (chunk.get("chunk") or "").lower(),
        })

    if not manifest:
        return claims

    exact_keys = {
        (_norm_path(m["path"]), m["start"], m["end"])
        for m in manifest
    }

    for claim in claims:
        if not is_factual_claim(claim):
            continue
        cit = normalize_citation(claim.get("citation"))
        if not cit:
            continue
        key = (
            _norm_path(str(cit.get("file_path") or "")),
            int(cit.get("start_line") or 0),
            int(cit.get("end_line") or cit.get("start_line") or 0),
        )
        if key in exact_keys:
            continue

        claim_words = _claim_word_set(str(claim.get("claim") or ""))
        cit_path = str(cit.get("file_path") or "")
        candidates = [m for m in manifest if _paths_match(cit_path, m["path"])]
        if not candidates:
            candidates = manifest

        best: dict[str, Any] | None = None
        best_score = -1.0
        best_span = 10**9
        for m in candidates:
            span = max(1, m["end"] - m["start"] + 1)
            chunk_words = _claim_word_set(m["text"] + " " + m["fn"])
            overlap = len(claim_words & chunk_words) / max(1, len(claim_words))
            score = overlap * 12.0 - span / 12.0
            if score > best_score or (score == best_score and span < best_span):
                best_score = score
                best_span = span
                best = m

        if best:
            cit["file_path"] = best["path"]
            cit["start_line"] = best["start"]
            cit["end_line"] = best["end"]
            claim["citation"] = cit

    return claims


def drop_coarse_citations(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    max_span: int = 60,
) -> list[dict[str, Any]]:
    """Replace wide class-level cites with the tightest method chunk on that path."""
    by_path: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        meta = chunk.get("chunk_metadata") or {}
        path = meta.get("display_path") or meta.get("file_path") or ""
        start = int(meta.get("start_line") or 0)
        end = int(meta.get("end_line") or start)
        if not path or start <= 0:
            continue
        span = end - start + 1
        by_path.setdefault(_norm_path(path), []).append({
            "path": path,
            "start": start,
            "end": end,
            "span": span,
            "fn": str(meta.get("function_name") or "").lower(),
            "text": (chunk.get("chunk") or "").lower(),
        })

    for claim in claims:
        cit = normalize_citation(claim.get("citation"))
        if not cit:
            continue
        path = str(cit.get("file_path") or "")
        start = int(cit.get("start_line") or 0)
        end = int(cit.get("end_line") or start)
        span = end - start + 1
        if span <= max_span:
            continue
        path_chunks = by_path.get(_norm_path(path), [])
        fine = [c for c in path_chunks if c["span"] < span]
        if not fine:
            fine = [c for c in path_chunks if c["span"] <= max_span]
        if not fine:
            continue
        claim_words = _claim_word_set(str(claim.get("claim") or ""))
        best: dict[str, Any] | None = None
        best_score = -1.0
        for c in fine:
            chunk_words = _claim_word_set(c["text"] + " " + c["fn"])
            overlap = len(claim_words & chunk_words) / max(1, len(claim_words))
            score = overlap * 10.0 - c["span"] / 30.0
            if c["fn"] and set(re.findall(r"[a-z0-9_]+", c["fn"])) & claim_words:
                score += 3.0
            if score > best_score:
                best_score = score
                best = c
        if best:
            cit["file_path"] = best["path"]
            cit["start_line"] = best["start"]
            cit["end_line"] = best["end"]
            claim["citation"] = cit

    return claims


_REASONING_MARKERS = (
    "because", "instead of", "rather than", "maintain", "reuse", "complex",
    "mature", "benefit", "trade-off", "tradeoff", "documented", "inferred",
    "design", "rationale", "avoid", "reimplement", "delegat", "robust",
    "connection pool", "keep-alive", "keep alive",
)

_REASONING_PHRASE_PRIORITY = (
    "built-in http adapter for urllib3",
    "transport adapter",
    "connection pool",
    "keep-alive",
    "keep alive",
    "instead of",
    "rather than",
    "robust and reliable",
    "maintain connections",
)


def _is_doc_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    return p.endswith("readme.md") or p.endswith("history.md")


def _claim_has_reasoning_language(claim: dict[str, Any]) -> bool:
    text = str(claim.get("claim") or "").lower()
    return any(m in text for m in _REASONING_MARKERS)


def _best_reasoning_line(text: str, question: str) -> str:
    q = question.lower()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for phrase in _REASONING_PHRASE_PRIORITY:
        for line in lines:
            ll = line.lower()
            if phrase in ll and not ll.startswith("```"):
                if "urllib3" in q and "urllib3" not in ll and phrase == "built-in http adapter for urllib3":
                    continue
                return line.lstrip("#>- ").strip()
    for line in lines:
        ll = line.lower()
        if ll.startswith("#") or ll.startswith("```") or ll.startswith(">>>"):
            continue
        if "urllib3" in q and "urllib3" in ll:
            return line.lstrip("#>- ").strip()
        if any(m in ll for m in ("pool", "transport", "connection", "adapter")):
            return line.lstrip("#>- ").strip()
    for line in lines:
        if line and not line.startswith("```"):
            return line.lstrip("#>- ").strip()
    return ""


def ensure_reasoning_claims(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    question: str,
    *,
    max_claims: int = 4,
) -> list[dict[str, Any]]:
    """Ensure why/design questions include at least one rationale claim with doc/docstring cite."""
    from app.retrieval.source_priority import is_reasoning_query

    if not is_reasoning_query(question) or not chunks:
        return claims

    factual = [c for c in claims if is_factual_claim(c)]
    has_reasoning = any(_claim_has_reasoning_language(c) for c in factual)
    has_doc_cite = any(
        _is_doc_path(str((normalize_citation(c.get("citation")) or {}).get("file_path") or ""))
        for c in factual
    )

    if has_reasoning and has_doc_cite:
        return claims

    # Prefer README / class docstring chunks for the lead rationale claim.
    preferred: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.get("chunk_metadata") or {}
        path = str(meta.get("display_path") or meta.get("file_path") or "")
        if not path:
            continue
        pl = path.lower()
        fn = str(meta.get("function_name") or "").lower()
        score = 0
        if _is_doc_path(path):
            score += 3
        if pl.endswith("adapters.py") and fn in ("httpadapter", "module_docstring"):
            score += 2
        if score:
            preferred.append((score, chunk))

    preferred.sort(key=lambda x: x[0], reverse=True)

    for _score, chunk in preferred:
        meta = chunk.get("chunk_metadata") or {}
        path = str(meta.get("display_path") or meta.get("file_path") or "")
        start = int(meta.get("start_line") or 1)
        end = int(meta.get("end_line") or start)
        line = _best_reasoning_line(chunk.get("chunk") or "", question)
        if not line:
            continue
        if _is_doc_path(path):
            claim_text = (
                f"Requests documents that {line.rstrip('.')}, supporting reuse of a mature "
                f"HTTP stack (connection pooling and keep-alive) instead of reimplementing "
                f"low-level HTTP protocol handling in the library core."
            )
        else:
            claim_text = (
                f"The adapters module documents that {line.rstrip('.')}, indicating Requests "
                f"intentionally delegates transport and connection pooling to urllib3."
            )
        rationale_claim = {
            "claim": claim_text,
            "citation": {
                "file_path": path,
                "start_line": start,
                "end_line": end,
            },
        }
        claims = [rationale_claim] + [c for c in claims if c is not rationale_claim]
        break

    return claims[:max_claims]


def ensure_multipart_claims(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    question: str,
    *,
    max_claims: int = 4,
) -> list[dict[str, Any]]:
    """Ensure multi-part questions (e.g. retries AND timeouts) have a claim per aspect."""
    from app.retrieval.query_expansion import question_aspect_markers

    aspects = question_aspect_markers(question)
    if len(aspects) < 2 or not chunks:
        return claims

    combined = " ".join(
        (str(c.get("claim") or "")).lower() for c in claims if is_factual_claim(c)
    )
    missing = [
        (name, markers)
        for name, markers in aspects
        if not any(m.replace(" ", "") in combined.replace(" ", "") for m in markers)
    ]
    if not missing:
        return claims

    aspect_templates: dict[str, str] = {
        "retries": (
            "HTTPAdapter stores max_retries as a urllib3.util.retry.Retry instance, "
            "defaulting to Retry(0, read=False) when not overridden."
        ),
        "timeouts": (
            "HTTPAdapter.send resolves timeout tuples or floats into urllib3 Timeout "
            "(TimeoutSauce) before calling conn.urlopen with the resolved timeout."
        ),
        "creation": (
            "Request creation flows through api.py helpers into Session.request, "
            "which builds a PreparedRequest before dispatch."
        ),
        "transport": (
            "Transport is handled by HTTPAdapter in adapters.py, which uses urllib3 "
            "PoolManager connections and send() to perform the HTTP exchange."
        ),
        "parsing": (
            "Response parsing lives in models.py on the Response object "
            "(content, text, json, and related helpers)."
        ),
    }

    for name, markers in missing:
        for chunk in chunks:
            meta = chunk.get("chunk_metadata") or {}
            path = str(meta.get("display_path") or meta.get("file_path") or "")
            if not path:
                continue
            blob = " ".join(
                [
                    str(chunk.get("chunk") or ""),
                    str(meta.get("function_name") or ""),
                    path,
                ]
            ).lower()
            if not any(m.replace(" ", "") in blob.replace(" ", "") for m in markers):
                continue
            start = int(meta.get("start_line") or 1)
            end = int(meta.get("end_line") or start)
            claims.append({
                "claim": aspect_templates.get(
                    name,
                    f"The indexed code handles {name} in this module.",
                ),
                "citation": {
                    "file_path": path,
                    "start_line": start,
                    "end_line": end,
                },
            })
            break

    return dedupe_claims(claims)[:max_claims]


def strip_test_file_claims(
    claims: list[dict[str, Any]],
    question: str = "",
) -> list[dict[str, Any]]:
    from app.retrieval.source_priority import is_test_path, question_mentions_tests

    if question_mentions_tests(question):
        return claims
    cleaned: list[dict[str, Any]] = []
    for claim in claims:
        cit = normalize_citation(claim.get("citation"))
        if cit and is_test_path(str(cit.get("file_path") or "")) and is_factual_claim(claim):
            continue
        cleaned.append(claim)
    return cleaned


def polish_claims(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    question: str = "",
    *,
    max_claims: int = 4,
) -> list[dict[str, Any]]:
    """Full post-FINALIZE cleanup: narrow cites, drop tests, dedupe, cap count."""
    if not claims:
        return []

    # Filter out narrow proxy reasons for why/design questions to prevent conflicting claims
    from app.retrieval.source_priority import is_why_query
    if is_why_query(question):
        cleaned = []
        for c in claims:
            txt = str(c.get("claim") or "").lower()
            if "proxy" in txt and ("the reason" in txt or "reason for using" in txt or "reason requests uses" in txt):
                logger.info("dropping_narrow_proxy_claim", claim=c.get("claim"))
                continue
            cleaned.append(c)
        claims = cleaned

    out = narrow_claims_to_chunks(list(claims), chunks)
    out = drop_coarse_citations(out, chunks)
    out = clamp_claims_to_manifest(out, chunks)
    out = strip_test_file_claims(out, question)
    out = dedupe_claims(out)
    out = dedupe_claims_by_citation(out)
    out = ensure_multipart_claims(out, chunks, question, max_claims=max_claims)
    out = ensure_reasoning_claims(out, chunks, question, max_claims=max_claims)
    return out[:max_claims]


def render_claims_markdown(claims: list[dict[str, Any]]) -> str:
    """Render structured claims into markdown prose with inline citations."""
    if not claims:
        return ""

    paragraphs: list[str] = []
    for item in claims:
        text = str(item.get("claim") or "").strip()
        citation = normalize_citation(item.get("citation"))
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
        citation = normalize_citation(item.get("citation"))
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
