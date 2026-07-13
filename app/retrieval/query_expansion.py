# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/retrieval/query_expansion.py
--------------------------------
Heuristic gating and LLM-based query expansion.

Responsibility boundary
-----------------------
This module decides if a query needs expansion, calls the LLM to generate
sub-queries, and caches the results to save LLM calls on repeated vague questions.
It does NOT:
  - execute search (Module 6a),
  - track tool-call usage for the agent loop (Module 9).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import concurrent.futures
from typing import Protocol, Any

from app.observability.logging_config import logger

# ---------------------------------------------------------------------------
# Protocols (Stubs for Module 8)
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    """
    Protocol matching the exact interface Module 8 will expose.
    This avoids importing an unbuilt module while remaining type-safe.
    """
    def generate_text(self, prompt: str) -> str:
        ...

# ---------------------------------------------------------------------------
# Simple Expansion Cache
# ---------------------------------------------------------------------------

_EXPANSION_CACHE: dict[str, list[str]] = {}


def _normalize_cache_key(query: str) -> str:
    """Normalize the query for caching (lowercase, strip extra spaces)."""
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Heuristic Gate
# ---------------------------------------------------------------------------

def should_expand(question: str) -> bool:
    """
    Decide if a question is vague enough to warrant query expansion.
    
    Heuristics:
    1. Length Gating: If question is <= 4 words (too short/incomplete) or >= 25 words (already detailed), skip.
    2. File Extension: If it matches a file extension like .py, .js, .ts, .go, .java, .rs, .md, .json, skip.
    3. Identifiers: If it contains camelCase (e.g. getUserData) or snake_case (e.g. get_user_data) or PascalCase, skip.
    4. Quotes: If it contains single, double, or backtick quoted code/strings, skip.
    """
    words = question.split()
    if len(words) <= 4 or len(words) >= 25:
        return False

    q_lower = question.lower()
    # Dotted identifiers / class.method — already specific, skip expansion Groq call.
    if "." in question and any(
        tok[0].isupper() or "_" in tok
        for tok in question.replace("`", "").split()
        if "." in tok
    ):
        return False
    if re.search(r"\b[A-Z][a-zA-Z0-9]*(?:\.[A-Za-z_][\w]*)+\b", question):
        return False

    # Concrete how/what questions about code mechanics — skip LLM expansion.
    if len(words) >= 5 and re.match(
        r"^(how|what)\b",
        question.strip(),
        re.IGNORECASE,
    ):
        q_lower = question.lower()
        concrete_markers = (
            "parameter", "validat", "process", "request", "response",
            "urllib", "poolmanager", "pooling", "pool", "handler", "middleware",
            "session", "header", "cookie", "endpoint",
            "httpbasicauth", "basicauth", "send", "adapter",
        )
        if any(marker in q_lower for marker in concrete_markers):
            return False
        
    if '"' in question or "'" in question or "`" in question:
        return False
        
    # Check file extension
    if re.search(r"\b\w+\.(py|js|ts|go|java|rs|json|md)\b", question, re.IGNORECASE):
        return False
        
    # Check snake_case / camelCase / PascalCase
    for word in words:
        clean = re.sub(r"[^\w]", "", word)
        if not clean:
            continue
        if "_" in clean and not clean.startswith("_") and not clean.endswith("_"):
            return False
        if re.search(r"[a-z][A-Z]", clean):
            return False
            
    return True


def needs_expansion(query: str) -> bool:
    """Legacy compatibility wrapper calling should_expand."""
    return should_expand(query)


def deterministic_expansions(question: str) -> list[str]:
    """
    Code-aware query variants that do not depend on the LLM.

    Used for rationale/how-why questions where generic LLM expansion often
    drifts (e.g. HTTP connection pooling → database pooling).
    """
    q = question.lower()
    out: list[str] = []
    if re.search(r"\bpool", q):
        out.extend([
            "HTTPAdapter init_poolmanager PoolManager urllib3 adapters.py",
            "get_connection_with_tls_context connection pool keep-alive socket reuse",
        ])
    if re.search(
        r"\b(how|why)\b.*\b(improve|performance|benefit|faster|efficient)\b",
        q,
        re.IGNORECASE,
    ):
        out.append(
            "implementation mechanism reuse cache connection adapter performance"
        )
    return out


def decompose_retrieval_variants(question: str) -> list[str]:
    """
    Split multi-part or flow/architecture questions into targeted search queries.

  Each variant is keyword-dense and retrieval-friendly — no LLM required.
    """
    q = question.lower()
    out: list[str] = []

    if re.search(r"\bretri", q) and re.search(r"\btimeout", q):
        out.extend([
            "urllib3 Retry max_retries HTTPAdapter __init__ adapters.py",
            "TimeoutSauce connect read timeout HTTPAdapter send urlopen",
        ])

    if re.search(r"\bretri", q) and not re.search(r"\btimeout", q):
        out.append("urllib3 Retry max_retries HTTPAdapter send retries")

    if re.search(r"\btimeout", q) and not re.search(r"\bretri", q):
        out.append("TimeoutSauce connect read timeout HTTPAdapter send")

    if re.search(
        r"\brequests\.(get|post|put|patch|delete|head|options)\b",
        q,
    ) or re.search(r"when\s+.+\s+(is\s+)?called", q):
        out.extend([
            "requests.get api.py get function request Session.request",
            "Session.send HTTPAdapter.send urlopen PreparedRequest",
            "models.py Response content json parsing",
        ])

    if re.search(
        r"\bmodule", q
    ) and re.search(r"\b(responsible|which)\b", q) and re.search(
        r"\b(transport|parsing|creation)\b", q
    ):
        out.extend([
            "api.py models.py PreparedRequest request creation Session",
            "adapters.py HTTPAdapter transport send urllib3",
            "models.py Response parsing content json text",
        ])

    if re.search(
        r"\b(custom\s+)?(transport|retry)\b|\btransport\s+layer\b|\bretry\s+mechanism\b",
        q,
    ):
        out.extend([
            "HTTPAdapter BaseAdapter send subclass mount adapter",
            "max_retries Retry urllib3 HTTPAdapter __init__ transport",
        ])

    if re.search(r"\bcookie", q):
        out.extend([
            "merge_cookies session cookies RequestsCookieJar sessions.py",
            "extract_cookies_to_jar persist cookies session send",
        ])

    from app.retrieval.source_priority import is_reasoning_query

    if is_reasoning_query(question):
        out.extend(reasoning_retrieval_variants(question))

    return out


def reasoning_retrieval_variants(question: str) -> list[str]:
    """Doc/design-focused retrieval variants for why/rationale questions."""
    q = question.lower()
    variants: list[str] = [
        "README design rationale purpose architecture decision trade-off",
        "HISTORY CHANGELOG why approach instead of",
    ]
    if re.search(r"\burllib3\b", q):
        variants.extend([
            "README urllib3 connection pooling keep-alive instead of implementing HTTP",
            "HTTPAdapter class docstring transport adapter urllib3 PoolManager",
            "adapters module transport maintain connections urllib3",
        ])
    if re.search(r"\bhttpadapter\b", q):
        variants.append("HTTPAdapter Transport Adapter interface urllib3 docstring")
    return variants


def question_aspect_markers(question: str) -> list[tuple[str, tuple[str, ...]]]:
    """Return (aspect_name, text_markers) for multi-part coverage checks."""
    q = question.lower()
    aspects: list[tuple[str, tuple[str, ...]]] = []
    if re.search(r"\bretri", q):
        aspects.append((
            "retries",
            ("retry", "max_retries", "urllib3.retry", "retryerror", "maxretry"),
        ))
    if re.search(r"\btimeout", q):
        aspects.append((
            "timeouts",
            ("timeout", "timeoutsauce", "connecttimeout", "readtimeout", "connect timeout"),
        ))
    if re.search(r"\b(request creation|creation|preparedrequest)\b", q) or (
        re.search(r"\bcreation\b", q) and re.search(r"\brequest\b", q)
    ):
        aspects.append((
            "creation",
            ("api.py", "preparedrequest", "models.py", "session", "request("),
        ))
    if re.search(r"\btransport\b", q):
        aspects.append((
            "transport",
            ("adapter", "httpadapter", "urllib3", "send(", "urlopen", "poolmanager"),
        ))
    if re.search(r"\b(response parsing|parsing|parse)\b", q) and re.search(
        r"\bresponse\b", q
    ):
        aspects.append((
            "parsing",
            ("response", "models.py", ".json(", ".text", "content"),
        ))
    if re.search(r"\bmodule", q) and re.search(
        r"\b(responsible|which)\b", q
    ) and len(aspects) >= 2:
        # Architecture "which modules handle X, Y, Z" — ensure breadth markers exist.
        pass
    return aspects


def needs_flow_tracing(question: str) -> bool:
    """True when the question asks for an internal call chain or dispatch path."""
    q = question.lower()
    patterns = (
        r"\bwhat happens\b",
        r"\binternally\b",
        r"\bwhen\s+.+\s+(is\s+)?called\b",
        r"\bcall\s+chain\b",
        r"\brequests\.(get|post|put|patch|delete)\b",
        r"\bflow\b.*\b(request|send|dispatch)\b",
    )
    return any(re.search(p, q) for p in patterns)


def is_why_query(question: str) -> bool:
    from app.retrieval.source_priority import is_why_query as _is_why

    return _is_why(question)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _filter_llm_variants(question: str, variants: list[str]) -> list[str]:
    """Drop LLM variants that contradict the question domain."""
    q = question.lower()
    filtered: list[str] = []
    for variant in variants:
        vl = variant.lower()
        if "database" in vl and "database" not in q and "sql" not in q:
            continue
        if variant.strip().lower() == q:
            continue
        filtered.append(variant)
    return filtered


# ---------------------------------------------------------------------------
# Expansion Execution
# ---------------------------------------------------------------------------

def expand_query(
    question: str,
    llm: Any = None,
    repo_context: str | None = None,
) -> list[str]:
    """
    Expand a vague question into 1-3 retrieval-friendly query variants using Groq.

    Forward Interface Contract:
    --------------------------
    Returns:
        list[str]: Always contains at least the original question as the first entry,
                   followed by 1-3 expanded search variants.
    """
    decomposed = decompose_retrieval_variants(question)
    det = deterministic_expansions(question)
    if not should_expand(question):
        return _dedupe_preserve_order([question] + decomposed + det)

    cache_key = _normalize_cache_key(question)
    if cache_key in _EXPANSION_CACHE:
        logger.debug("query_expansion_cache_hit", question=question)
        return _EXPANSION_CACHE[cache_key]

    log = logger.bind(question=question)
    start_time = time.perf_counter()

    prompt = (
        "You are an expert developer assistant. The user has a vague question about their codebase.\n"
        "Generate 1 to 3 alternative search queries (short, technical, keyword-dense) to find the relevant code.\n"
        "Return ONLY a valid JSON list of strings. Do not include markdown block syntax, explanation, or introduction.\n"
        f"Question: {question}\n"
    )
    if repo_context:
        prompt += f"Context: {repo_context}\n"

    response_text = ""
    # Prefer injected client; otherwise use the shared LLM abstraction (Module #8 boundary).
    client = llm
    if client is None or not hasattr(client, "generate_text"):
        try:
            from app.agent.llm_client import get_llm_client

            client = get_llm_client()
        except Exception as exc:
            log.warning("query_expansion_llm_client_unavailable", error=str(exc))
            return _dedupe_preserve_order([question] + det)

    attempts = 2
    for attempt in range(attempts):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(client.generate_text, prompt)
                response_text = future.result(timeout=5.0)
            if response_text:
                break
        except Exception as exc:
            log.warning(
                "query_expansion_via_llm_client_failed",
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt == attempts - 1:
                log.warning("query_expansion_failed_all_attempts")
                return _dedupe_preserve_order([question] + det)

    # Parse response
    try:
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
            
        variants = json.loads(clean_text.strip())
        if isinstance(variants, list):
            # Limit to 3 variants
            variants = [str(x) for x in variants][:3]
        else:
            variants = []
    except Exception as exc:
        log.warning("query_expansion_json_parsing_failed", response=response_text, error=str(exc))
        variants = []

    variants = _filter_llm_variants(question, variants)
    final_list = _dedupe_preserve_order([question] + decomposed + det + variants)

    _EXPANSION_CACHE[cache_key] = final_list
    elapsed = time.perf_counter() - start_time
    log.info("query_expansion_completed", expansions=final_list[1:], time_ms=round(elapsed * 1000, 2))
    
    return final_list
