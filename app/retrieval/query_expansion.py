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

from app.config import settings
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
    if not should_expand(question):
        return [question]

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
            return [question]

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
                return [question]

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

    # Always include the original query as the first item
    final_list = [question] + [v for v in variants if v.strip() and v != question]
    
    _EXPANSION_CACHE[cache_key] = final_list
    elapsed = time.perf_counter() - start_time
    log.info("query_expansion_completed", expansions=final_list[1:], time_ms=round(elapsed * 1000, 2))
    
    return final_list
