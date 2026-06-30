"""
app/agent/retrieval_prefetch.py
---------------------------------
Enhanced retrieve-then-read: symbol-boosted hits + optional multi-hop search
for flow/architecture questions.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app.agent.cache_keys import normalize_cache_key
from app.agent.symbol_lookup import resolve_symbol_location
from app.agent.tools import execute_tool_with_retry

_FLOW_RE = re.compile(
    r"\b(how does|how do|ultimately|flow|send|dispatch|handled|persist|work)\b",
    re.IGNORECASE,
)
_SKIP_SYMBOLS = frozenset({
    "HTTP", "SSL", "URL", "API", "JSON", "GitHub", "Python", "Session",
})


def extract_query_symbols(question: str) -> list[str]:
    """PascalCase types and explicit function calls from the question."""
    seen: set[str] = set()
    out: list[str] = []
    for sym in re.findall(r"\b[A-Z][a-zA-Z_]\w*\b", question):
        if sym not in _SKIP_SYMBOLS and sym not in seen:
            seen.add(sym)
            out.append(sym)
    for sym in re.findall(r"\b([a-z_][a-zA-Z0-9_]*)\(\)", question):
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def needs_multihop_search(question: str) -> bool:
    return bool(_FLOW_RE.search(question))


def _norm_fp(fp: str) -> str:
    return fp.replace("\\", "/").lstrip("./").lower()


def symbol_boost_hits(
    repo_id: str,
    question: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepend definition locations for symbols named in the question."""
    boosted: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for sym in extract_query_symbols(question)[:4]:
        kind = "class" if sym[0].isupper() else "function"
        loc = resolve_symbol_location(repo_id, sym, kind=kind)
        if not loc:
            continue
        fp = loc.get("file_path") or ""
        norm = _norm_fp(fp)
        if not norm or norm in seen_paths:
            continue
        seen_paths.add(norm)
        boosted.append({
            "file_path": fp,
            "function_name": loc.get("function_name") or sym,
            "start_line": loc.get("start_line"),
            "end_line": loc.get("end_line"),
            "rerank_score": 0.92,
            "chunk": f"Definition of {sym} in {fp}",
        })

    merged: list[dict[str, Any]] = []
    for h in boosted + hits:
        fp = h.get("file_path") or ""
        norm = _norm_fp(fp)
        if norm and norm in seen_paths and h not in boosted:
            continue
        if norm:
            seen_paths.add(norm)
        merged.append(h)
    return merged[:10]


def _merge_hits(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for h in primary + secondary:
        norm = _norm_fp(h.get("file_path") or "")
        if norm and norm in seen:
            continue
        if norm:
            seen.add(norm)
        out.append(h)
    return out[:10]


def run_prefetch(
    question: str,
    repo_id: str,
    log: Any,
    *,
    hits_from_result: Callable[[dict[str, Any]], list[dict[str, Any]]],
    reorder_hits: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]],
    tool_cache: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], float]:
    """Execute hybrid search prefetch with symbol boost and optional second hop."""
    prefetch_input = {"query": question, "top_k": 5}
    try:
        result = execute_tool_with_retry("search_code", prefetch_input, repo_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("prefetch_failed", error=str(exc))
        return None, [], 0.0

    tool_cache[normalize_cache_key("search_code", prefetch_input)] = result
    hits = reorder_hits(question, hits_from_result(result))
    hits = symbol_boost_hits(repo_id, question, hits)

    if needs_multihop_search(question):
        symbols = extract_query_symbols(question)
        follow_up = symbols[0] if symbols else None
        if not follow_up and hits:
            follow_up = hits[0].get("function_name") or question.split()[0]
        if follow_up:
            second_input = {"query": follow_up, "top_k": 5}
            cache_key = normalize_cache_key("search_code", second_input)
            if cache_key not in tool_cache:
                try:
                    second_result = execute_tool_with_retry("search_code", second_input, repo_id)
                    tool_cache[cache_key] = second_result
                except Exception as exc:  # noqa: BLE001
                    log.warning("prefetch_second_hop_failed", error=str(exc))
                    second_result = None
            else:
                second_result = tool_cache[cache_key]
            if second_result:
                hits2 = reorder_hits(follow_up, hits_from_result(second_result))
                hits = _merge_hits(hits, hits2)
                log.info("prefetch_second_hop", query=follow_up, merged=len(hits))

    best = max((float(h.get("rerank_score") or 0.0) for h in hits), default=0.0)
    log.info("prefetch_completed", hits=len(hits), best_score=round(best, 3))
    return result, hits, best
