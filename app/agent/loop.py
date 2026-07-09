# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/loop.py
-----------------
The core agentic RAG loop.

Responsibility boundary
-----------------------
This module orchestrates the iterative tool-calling loop, tracks the cache budget,
compresses context when needed, and hands off the final trace to Module 9b.

Design Constraint: No Hardcoded Router
--------------------------------------
Tool selection is entirely the LLM's job, guided only by the system prompt and
tool descriptions. We do not use a classifier to route intents. If tool choice is
unreliable, the fix is sharpening the prompt/tool descriptions, not adding an
external router.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from app.agent.cache_keys import normalize_cache_key
from app.agent.context_manager import compress_older_tool_results
from app.agent.llm_client import get_llm_client, ProviderError, RateLimitError
from app.agent.system_prompt import (
    SYSTEM_PROMPT,
    DIRECTIVE_BUDGET_EXHAUSTED,
    DIRECTIVE_FORCE_SEARCH,
    DIRECTIVE_TOOL_FORMAT_ERROR,
)
from app.agent.tools import TOOL_DEFINITIONS, execute_tool_with_retry
from app.agent.confidence import validate_and_return, _build_sources_from_hits
from app.config import settings
from app.observability.logging_config import logger


# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------

def _extract_retry_after(exc: Exception, default: float = 5.0) -> float:
    """
    Read the ``Retry-After`` header from a Groq 429 response if present,
    otherwise fall back to ``default`` seconds.

    The Groq SDK wraps the raw ``httpx.Response`` on ``exc.__cause__.response``
    so we walk the cause chain to find it.

    The return value is capped at 12 s so a large Retry-After (e.g. 60 s from
    a daily-quota exhaustion) never blows the frontend request timeout.
    """
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        response = getattr(cause, "response", None)
        if response is not None:
            headers = getattr(response, "headers", {})
            val = headers.get("retry-after") or headers.get("Retry-After")
            if val:
                try:
                    return min(max(1.0, float(val)), 12.0)
                except (ValueError, TypeError):
                    pass
    return default

# ---------------------------------------------------------------------------
# Core Loop
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Core Loop
# ---------------------------------------------------------------------------

from app.cache.tool_cache import ToolCache

# Shared tool cache: in-process L1 + Redis when available
_TOOL_CACHE = ToolCache()


def _hits_from_search_result(tool_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized retrieval hits from a search_code tool result."""
    hits: list[dict[str, Any]] = []
    for r in tool_result.get("results", []):
        meta = r.get("metadata") or {}
        fp = (
            meta.get("display_path")
            or meta.get("normalized_path")
            or meta.get("file_path")
            or ""
        )
        hits.append({
            "file_path": fp,
            "function_name": meta.get("function_name"),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "rerank_score": r.get("rerank_score", 0.0),
            "chunk": r.get("chunk") or "",
        })
    return hits


def _reorder_hits_for_question(question: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface definition chunks and src/ files ahead of test/helper matches."""
    q_caps = set(re.findall(r"\b[A-Z][a-zA-Z_]\w*\b", question))

    def rank(h: dict[str, Any]) -> float:
        base = float(h.get("rerank_score", 0))
        chunk = h.get("chunk") or ""
        fn = h.get("function_name") or ""
        path = (h.get("file_path") or "").lower()
        for w in q_caps:
            if f"class {w}" in chunk:
                base += 0.18
            if fn == w or fn.startswith(f"{w}."):
                base += 0.12
        if "/tests/" in path or path.startswith("tests/"):
            base -= 0.22
        elif "/src/" in path or path.startswith("src/"):
            base += 0.06
        return base

    return sorted(hits, key=rank, reverse=True)


def _prefetch_context(question: str, repo_id: str, log: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]], float]:
    """
    Deterministic retrieve-then-read with symbol boost + multi-hop for flow questions.
    """
    from app.agent.retrieval_prefetch import run_prefetch

    return run_prefetch(
        question,
        repo_id,
        log,
        hits_from_result=_hits_from_search_result,
        reorder_hits=_reorder_hits_for_question,
        tool_cache=_TOOL_CACHE,
    )


def answer_question(
    question: str,
    repo_id: str,
    max_iterations: int | None = None,
    max_tool_calls: int | None = None,
    max_total_tokens: int | None = None,
    context_compression_threshold: float | None = None,
    request_id: str | None = None,
    max_wall_seconds: float | None = None,
    chat_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    The iterative tool-calling agent loop.
    """
    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("run_agent_loop") as span:
        span.set_attribute("repo_id", repo_id)
        span.set_attribute("request_id", request_id or "unknown")
        
        return _answer_question_inner(
            question, repo_id, max_iterations, max_tool_calls, 
            max_total_tokens, context_compression_threshold, 
            request_id, max_wall_seconds, span, chat_history
        )

def _answer_question_inner(
    question: str,
    repo_id: str,
    max_iterations: int | None = None,
    max_tool_calls: int | None = None,
    max_total_tokens: int | None = None,
    context_compression_threshold: float | None = None,
    request_id: str | None = None,
    max_wall_seconds: float | None = None,
    span: Any = None,
    chat_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if max_iterations is None:
        max_iterations = settings.MAX_AGENT_ITERATIONS
    if max_tool_calls is None:
        max_tool_calls = settings.MAX_TOOL_CALLS
    if max_total_tokens is None:
        max_total_tokens = settings.MAX_TOTAL_TOKENS
    if context_compression_threshold is None:
        context_compression_threshold = settings.CONTEXT_COMPRESSION_THRESHOLD
    if max_wall_seconds is None:
        max_wall_seconds = settings.AGENT_MAX_SECONDS

    log = logger.bind(repo_id=repo_id, request_id=request_id)
    llm = get_llm_client()
    
    messages = []
    if chat_history:
        messages.extend(chat_history)
        
    messages.append({"role": "user", "content": question})
    
    # 1. Sync-status gate (stubbed check for Module 3 interaction)
    # The actual implementation would read from a db or status file.
    import os
    from pathlib import Path
    
    start_time = time.time()
    deadline = start_time + max_wall_seconds
    
    status_file = Path(settings.REPOS_PATH) / repo_id / "sync_status.json"
    if status_file.exists():
        try:
            status_data = json.loads(status_file.read_text())
            if status_data.get("status") != "synced":
                log.warning("repo_not_synced", status=status_data.get("status"))
                return {"error": "Repository is not fully synced. Please wait for ingestion to complete."}
        except Exception:
            pass

    trace: list[dict[str, Any]] = []
    best_retrieval_score: float = 0.0
    retrieval_hits: list[dict[str, Any]] = []
    tool_calls_made = 0
    total_tokens_used = 0
    pending_force_search = False
    pending_tool_format_retry = False

    # Retrieve-then-read: always ground the first turn deterministically so the
    # answer never depends on the model deciding to call search_code itself.
    prefetch_result, prefetch_hits, prefetch_best = _prefetch_context(question, repo_id, log)
    if prefetch_result is not None:
        retrieval_hits.extend(prefetch_hits)
        best_retrieval_score = max(best_retrieval_score, prefetch_best)
        tool_calls_made += 1
        prefetch_id = f"call_{uuid.uuid4().hex[:8]}"
        messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": prefetch_id,
                "name": "search_code",
                "input": {"query": question, "top_k": 5},
            }],
        })
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": prefetch_id,
                "content": json.dumps(prefetch_result),
            }],
        })

    # Reset the wall-clock budget after prefetch: cold model loads (embedding +
    # cross-encoder) must not eat the model's reasoning time on the first request.
    deadline = time.time() + max_wall_seconds

    for iteration in range(max_iterations):
        if time.time() > deadline:
            log.warning("wall_clock_deadline_exceeded", iterations_done=iteration)
            return {
                "answer": "The request took too long to complete. The backend may be under heavy load or the AI provider is slow. Please try again in a moment.",
                "sources": [],
                "confidence": "low",
                "confidence_score": 0.0,
                "invalid_reference_ratio": None,
                "gated": True,
                "timed_out": True,
                "trace": trace,
                "iterations_used": iteration,
            }
        log.debug("agent_loop_iteration", iteration=iteration)

        # Dynamic system directives (never injected as user messages — those leak to UI)
        effective_system = SYSTEM_PROMPT
        if tool_calls_made >= max_tool_calls:
            effective_system += DIRECTIVE_BUDGET_EXHAUSTED
            available_tools = None
        else:
            available_tools = TOOL_DEFINITIONS
        if pending_force_search:
            effective_system += DIRECTIVE_FORCE_SEARCH
            pending_force_search = False
        if pending_tool_format_retry:
            effective_system += DIRECTIVE_TOOL_FORMAT_ERROR
            pending_tool_format_retry = False

        # Context compression check
        # Hardcoding a nominal max window (e.g., 8000) for the heuristic token check if max_total_tokens is a strict budget
        if total_tokens_used > context_compression_threshold * max_total_tokens:
            log.info("triggering_context_compression")
            keep_n = 1 if settings.LLM_PROVIDER.lower() == "groq" else 2
            compress_older_tool_results(messages, keep_last_n=keep_n)
            
        # LLM Call — retry once on rate-limit before giving up gracefully.
        try:
            res = llm.create(
                system=effective_system,
                messages=messages,
                tools=available_tools,
                max_tokens=700
            )
        except RateLimitError as e:
            retry_after = _extract_retry_after(e, default=5.0)
            # If the provider signals a long wait (daily quota, not per-minute blip),
            # retrying immediately after sleeping won't help — return the friendly
            # message right away so we don't burn the frontend's request timeout.
            _RATE_LIMIT_SKIP_RETRY_THRESHOLD = 20.0
            if retry_after > _RATE_LIMIT_SKIP_RETRY_THRESHOLD:
                log.warning(
                    "rate_limit_long_retry_after_skip",
                    retry_after_s=retry_after,
                    iteration=iteration,
                )
                return {
                    "answer": (
                        "The AI provider is temporarily rate-limited. "
                        "Please wait about 30 seconds and try again."
                    ),
                    "sources": _build_sources_from_hits(retrieval_hits, max_sources=3),
                    "confidence": "low",
                    "confidence_score": 0.0,
                    "invalid_reference_ratio": None,
                    "gated": True,
                    "rate_limited": True,
                    "trace": trace,
                    "retrieval_hits": retrieval_hits,
                    "iterations_used": iteration,
                }
            log.warning(
                "rate_limit_retrying",
                retry_after_s=retry_after,
                iteration=iteration,
            )
            time.sleep(retry_after)
            try:
                res = llm.create(
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=available_tools,
                    max_tokens=700
                )
            except RateLimitError:
                # Second consecutive rate-limit — give up gracefully so the
                # caller can show a friendly message without a 500 crash.
                log.warning("rate_limit_exhausted_after_retry", iteration=iteration)
                return {
                    "answer": (
                        "The AI provider is temporarily rate-limited. "
                        "Please wait about 30 seconds and try again."
                    ),
                    "sources": _build_sources_from_hits(retrieval_hits, max_sources=3),
                    "confidence": "low",
                    "confidence_score": 0.0,
                    "invalid_reference_ratio": None,
                    "gated": True,
                    "rate_limited": True,
                    "trace": trace,
                    "retrieval_hits": retrieval_hits,
                    "iterations_used": iteration,
                }
        except ProviderError as e:
            if "tool_use_failed" in str(e):
                log.warning("llm_tool_formatting_error_retry", error=str(e))
                pending_tool_format_retry = True
                continue
            raise
        
        total_tokens_used += res.usage.get("input_tokens", 0) + res.usage.get("output_tokens", 0)
        
        trace.append({
            "iteration": iteration,
            "stop_reason": res.stop_reason,
            "usage": res.usage
        })
        
        # Append assistant response to messages
        messages.append({
            "role": "assistant",
            "content": res.content
        })
        
        if res.stop_reason != "tool_use":
            # Guard: Force at least one tool call on the first iteration to prevent lazy answers without sources
            if iteration == 0 and tool_calls_made == 0:
                log.info("forcing_tool_use_on_lazy_assistant")
                pending_force_search = True
                continue

            # Loop ends! Handoff to Module 9b
            log.info("agent_finished", iterations=iteration)

            if span:
                span.set_attribute("total_tokens_used", total_tokens_used)
                span.set_attribute("iterations", iteration)

            return validate_and_return(
                res.content, repo_id, trace, best_retrieval_score, retrieval_hits, question=question
            )
            
        # Process tool calls
        tool_results_blocks = []
        for block in res.content:
            if block["type"] == "tool_use":
                tool_name = block["name"]
                tool_input = block["input"]
                tool_id = block["id"]
                
                if tool_calls_made >= max_tool_calls:
                    tool_results_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps({"error": "budget_exceeded"}),
                    })
                    continue
                
                try:
                    cache_key = normalize_cache_key(tool_name, tool_input)
                    if cache_key in _TOOL_CACHE:
                        log.debug("tool_cache_hit", tool_name=tool_name)
                        tool_result = _TOOL_CACHE[cache_key]
                    else:
                        log.info("tool_execution", tool_name=tool_name, tool_input=tool_input)
                        tool_result = execute_tool_with_retry(tool_name, tool_input, repo_id)
                        tool_calls_made += 1
                        _TOOL_CACHE[cache_key] = tool_result

                        if tool_name == "search_code" and "results" in tool_result:
                            for r in tool_result["results"]:
                                score = r.get("rerank_score", 0.0)
                                if score > best_retrieval_score:
                                    best_retrieval_score = score
                                meta = r.get("metadata") or {}
                                fp = (
                                    meta.get("display_path")
                                    or meta.get("normalized_path")
                                    or meta.get("file_path")
                                    or ""
                                )
                                retrieval_hits.append({
                                    "file_path": fp,
                                    "function_name": meta.get("function_name"),
                                    "start_line": meta.get("start_line"),
                                    "end_line": meta.get("end_line"),
                                    "rerank_score": score,
                                    "chunk": r.get("chunk") or "",
                                })
                except Exception as exc:
                    log.error("tool_execution_crashed", tool_name=tool_name, error=str(exc))
                    tool_result = {"error": f"Tool execution failed unexpectedly: {exc}"}
                
                # We package the result into Anthropic's expected tool_result block
                tool_results_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(tool_result)
                })
                
        if tool_results_blocks:
            messages.append({
                "role": "user",
                "content": tool_results_blocks
            })

    # If we fell out of the loop without ending
    log.warning("max_iterations_exhausted")
    return {
        "error": "Could not resolve within the iteration limit.",
        "trace": trace
    }
