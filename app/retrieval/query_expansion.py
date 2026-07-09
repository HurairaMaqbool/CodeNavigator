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
from typing import Protocol

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

def needs_expansion(query: str) -> bool:
    """
    Returns True if the query is vague/conceptual and needs expansion.

    Expansion is skipped if the query is:
      1. Short (<= 6 words).
      2. Contains identifier-like tokens (snake_case, camelCase).
      3. Contains quoted strings.
    """
    words = query.split()
    
    # 1. Short queries are usually specific enough
    if len(words) <= 6:
        return False

    # 2. Contains quoted strings -> user knows exactly what they want
    if '"' in query or "'" in query or "`" in query:
        return False

    # 3. Contains identifier-shaped words (snake_case, camelCase, PascalCase)
    # We ignore standard English words.
    for word in words:
        # Strip punctuation from the word
        clean = re.sub(r"[^\w]", "", word)
        if not clean:
            continue
            
        # Check snake_case
        if "_" in clean and not clean.startswith("_") and not clean.endswith("_"):
            return False
            
        # Check camelCase / PascalCase
        # At least one lowercase followed by an uppercase
        if re.search(r"[a-z][A-Z]", clean):
            return False

    return True


# ---------------------------------------------------------------------------
# Expansion Execution
# ---------------------------------------------------------------------------

def expand_query(query: str, llm: LLMClient) -> list[str]:
    """
    Uses the LLM to generate 2-3 specific technical sub-queries from a vague one.
    Uses an internal memory cache to avoid duplicate calls.
    Returns the original query plus the expansions.
    """
    cache_key = _normalize_cache_key(query)
    if cache_key in _EXPANSION_CACHE:
        logger.debug("query_expansion_cache_hit", query=query)
        return _EXPANSION_CACHE[cache_key]

    log = logger.bind(query=query)
    log.info("query_expansion_started")
    start_time = time.perf_counter()

    prompt = (
        "You are an expert software engineer. The user asked a vague conceptual "
        "question about a codebase. Generate 2 or 3 specific, short, keyword-dense "
        "search queries that would help find the code related to their question.\n"
        "Return ONLY a JSON array of strings. No markdown formatting, no explanations.\n"
        f"Question: {query}\n"
    )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(llm.generate_text, prompt)
            response_text = future.result(timeout=5.0)
            
        # Strip possible markdown code blocks
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
            
        expansions = json.loads(clean_text.strip())
        
        if not isinstance(expansions, list):
            expansions = []
            
        # Ensure they are strings and limit to 3 max
        expansions = [str(x) for x in expansions][:3]
        
    except concurrent.futures.TimeoutError:
        log.warning("query_expansion_timeout", hint="LLM took more than 5s")
        expansions = []
    except Exception as exc:
        log.warning("query_expansion_failed", reason=str(exc))
        expansions = []

    # Always include the original query as the first item
    final_list = [query] + expansions
    
    _EXPANSION_CACHE[cache_key] = final_list
    elapsed = time.perf_counter() - start_time
    log.info("query_expansion_completed", expansions=expansions, time_ms=round(elapsed * 1000, 2))
    
    return final_list
