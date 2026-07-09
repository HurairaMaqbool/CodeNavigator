# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/loop.py
-----------------
Module #21 — Layer 7 Agentic Loop Engine (explicit state machine).

INTAKE → PLAN → ACT → OBSERVE → DECIDE → FINALIZE → VERIFY → RESPOND

Pure orchestration: retrieval/graph modules are called in ACT; Groq only in
PLAN (via query_expansion), DECIDE, and FINALIZE. Hard iteration cap from
settings.MAX_ITERATIONS.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.agent.llm_client import ProviderError, RateLimitError, get_llm_client
from app.config import settings
from app.ingestion.metadata_store import metadata_store
from app.observability.logging_config import logger

# Re-exported for tests and semantic_cache refresh (Module #24 integration).
from app.agent.context_manager import compress_older_tool_results  # noqa: F401
from app.agent.tools import execute_tool_with_retry  # noqa: F401
from app.cache.tool_cache import ToolCache

_TOOL_CACHE = ToolCache()

# OBSERVE context budget (~4 chars/token heuristic for English code).
_DEFAULT_CONTEXT_TOKEN_BUDGET = 4000
_DECIDE_MODEL = None  # settings.LLM_MODEL
_FINALIZE_MAX_TOKENS = 700
_GROQ_TIMEOUT_S = 25.0


# ---------------------------------------------------------------------------
# Forward stubs — Modules #24, #25, #26 (swap real implementations later)
# ---------------------------------------------------------------------------

def semantic_cache_lookup(repo_id: str, question: str) -> dict[str, Any] | None:
    """
    FORWARD STUB — Module #24 ``semantic_cache.lookup(repo_id, question)``.

    Returns a cached ``{answer, sources, confidence_score, gated}`` dict or None.
    """
    if not settings.SEMANTIC_CACHE_ENABLED:
        return None
    try:
        from app.agent.semantic_cache import SemanticCache, _get_repo_metadata
        from app.retrieval.embeddings import embed

        embedding = embed(question)
        cached = SemanticCache.find_nearest(repo_id, embedding)
        if not cached:
            return None
        meta = _get_repo_metadata(repo_id)
        if cached.get("repo_commit_hash") != meta.get("commit_hash", ""):
            return None
        payload = cached.get("answer")
        if isinstance(payload, dict) and payload.get("answer"):
            return {
                "answer": payload["answer"],
                "sources": payload.get("sources", []),
                "confidence_score": float(payload.get("confidence_score", 0.0)),
                "gated": bool(payload.get("gated", False)),
            }
    except Exception as exc:
        logger.debug("semantic_cache_stub_miss", error=str(exc))
    return None


def semantic_cache_store(repo_id: str, question: str, response: dict[str, Any]) -> None:
    """FORWARD STUB — Module #24 ``semantic_cache.store(repo_id, question, response)``."""
    if not settings.SEMANTIC_CACHE_ENABLED or response.get("gated"):
        return
    try:
        from app.agent.semantic_cache import SemanticCache, _get_repo_metadata
        from app.retrieval.embeddings import embed

        embedding = embed(question)
        meta = _get_repo_metadata(repo_id)
        SemanticCache.store(repo_id, embedding, response, meta.get("commit_hash", ""))
    except Exception as exc:
        logger.debug("semantic_cache_stub_store_skipped", error=str(exc))


def context_manager_assemble(
    chunks: list[dict[str, Any]],
    graph_context: str,
    *,
    max_tokens: int = _DEFAULT_CONTEXT_TOKEN_BUDGET,
) -> str:
    """
    FORWARD STUB — Module #25 ``context_manager.assemble_context(chunks, graph, max_tokens)``.

    Trims merged chunk text to a token budget before DECIDE/FINALIZE Groq calls.
    """
    budget_chars = max(500, max_tokens * 4)
    parts: list[str] = []
    used = 0
    for hit in chunks:
        text = hit.get("chunk") or ""
        if not text:
            continue
        meta = hit.get("chunk_metadata") or {}
        header = meta.get("display_path") or meta.get("file_path") or "chunk"
        block = f"### {header}\n{text}"
        if used + len(block) > budget_chars:
            remaining = budget_chars - used
            if remaining > 80:
                parts.append(block[:remaining] + "\n...[truncated]")
            break
        parts.append(block)
        used += len(block)
    if graph_context:
        parts.append(f"### Graph context\n{graph_context[:2000]}")
    return "\n\n".join(parts) if parts else "(no context retrieved)"


def confidence_verify(
    answer: str,
    sources: list[dict[str, Any]],
    *,
    best_retrieval_score: float,
    invalid_reference_ratio: float = 0.0,
) -> tuple[float, bool, str]:
    """
    FORWARD STUB — Module #26 ``confidence.verify_answer(...)``.

    Returns ``(confidence_score, gated, optional_disclaimer)``.
    """
    from app.agent.confidence import compute_confidence_score

    score = compute_confidence_score(
        invalid_reference_ratio,
        best_retrieval_score,
        min(len(sources), 3),
    )
    gated = score < settings.MIN_CONFIDENCE_SCORE
    disclaimer = ""
    if gated:
        disclaimer = "\n\n_(This answer had lower confidence — please verify against the cited sources.)_"
    return score, gated, disclaimer


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class AgentState(str, Enum):
    INTAKE = "INTAKE"
    PLAN = "PLAN"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    DECIDE = "DECIDE"
    FINALIZE = "FINALIZE"
    VERIFY = "VERIFY"
    RESPOND = "RESPOND"


@dataclass
class AgentContext:
    repo_id: str
    question: str
    session_id: str | None = None
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    query_variants: list[str] = field(default_factory=list)
    need_structural: bool = False
    chunks: list[dict[str, Any]] = field(default_factory=list)
    graph_context: str = ""
    assembled_context: str = ""
    enough_evidence: bool = False
    answer: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    gated: bool = False
    iteration: int = 0
    max_iterations: int = 0
    best_retrieval_score: float = 0.0
    cache_hit: bool = False
    error: str | None = None
    state_trace: list[str] = field(default_factory=list)
    groq_failed: bool = False
    rate_limited: bool = False
    timed_out: bool = False


_STATE_HANDLERS: dict[AgentState, Callable[[AgentContext], AgentState]] = {}


def _register(state: AgentState):
    def decorator(fn: Callable[[AgentContext], AgentState]):
        _STATE_HANDLERS[state] = fn
        return fn
    return decorator


def _transition(ctx: AgentContext, nxt: AgentState) -> AgentState:
    if ctx.session_id:
        try:
            from app.api.state_stream import emit

            if not ctx.state_trace:
                emit(ctx.session_id, AgentState.INTAKE.value)
            emit(ctx.session_id, nxt.value)
        except Exception as exc:
            logger.debug("state_stream_emit_skipped", error=str(exc))
    ctx.state_trace.append(nxt.value)
    return nxt


def _needs_structural_context(question: str) -> bool:
    q = question.lower()
    markers = (
        "caller", "callee", "depend", "dependency", "call graph", "who calls",
        "what calls", "import", "flow between", "architecture", "subgraph",
    )
    return any(m in q for m in markers)


def _groq_text(system: str, user: str, *, max_tokens: int = 256) -> str:
    """Bounded Groq call with retry-once (matches query_expansion pattern)."""
    llm = get_llm_client()
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            res = llm.create(
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
            )
            return "".join(
                block.get("text", "")
                for block in res.content
                if block.get("type") == "text"
            ).strip()
        except RateLimitError as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(min(5.0, 12.0))
                continue
            raise
        except ProviderError as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise
    raise ProviderError(str(last_exc) if last_exc else "Groq call failed")


def _hits_to_sources(chunks: list[dict[str, Any]], max_sources: int = 5) -> list[dict[str, Any]]:
    from app.agent.confidence import _build_sources_from_hits

    hits = []
    for c in chunks:
        meta = c.get("chunk_metadata") or {}
        hits.append({
            "file_path": meta.get("display_path") or meta.get("file_path") or "",
            "function_name": meta.get("function_name") or "",
            "start_line": meta.get("start_line") or 0,
            "end_line": meta.get("end_line") or 0,
            "rerank_score": float(c.get("score", 0.0)),
            "chunk": c.get("chunk") or "",
        })
    built = _build_sources_from_hits(hits, max_sources=max_sources)
    out: list[dict[str, Any]] = []
    for s in built:
        lines = s.get("lines")
        start_line = 0
        end_line = 0
        if lines and isinstance(lines, str) and "-" in lines:
            a, b = lines.split("-", 1)
            start_line, end_line = int(a), int(b)
        elif lines:
            start_line = end_line = int(lines)
        out.append({
            "file_path": s.get("file_path", ""),
            "function_name": s.get("function_name", ""),
            "start_line": start_line,
            "end_line": end_line,
        })
    return out


def _merge_search_results(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, int, int], dict[str, Any]] = {}
    for batch in batches:
        for hit in batch:
            meta = hit.get("chunk_metadata") or {}
            key = (
                meta.get("file_path", ""),
                int(meta.get("start_line") or 0),
                int(meta.get("end_line") or 0),
            )
            if key not in seen or float(hit.get("score", 0)) > float(seen[key].get("score", 0)):
                seen[key] = hit
    merged = list(seen.values())
    merged.sort(key=lambda h: float(h.get("score", 0.0)), reverse=True)
    return merged


@_register(AgentState.INTAKE)
def _handle_intake(ctx: AgentContext) -> AgentState:
  # Semantic cache first (zero Groq) — skip when multi-turn session history present.
    if not ctx.chat_history:
        cached = semantic_cache_lookup(ctx.repo_id, ctx.question)
        if cached:
            ctx.answer = cached["answer"]
            ctx.sources = cached.get("sources", [])
            ctx.confidence_score = float(cached.get("confidence_score", 0.0))
            ctx.gated = bool(cached.get("gated", False))
            ctx.cache_hit = True
            return _transition(ctx, AgentState.RESPOND)

    meta = metadata_store.get(ctx.repo_id)
    if meta is None or meta.sync_status != "synced":
        status = meta.sync_status if meta else "unknown"
        ctx.answer = (
            f"This repository is still indexing (status: {status}). "
            "Please wait for ingestion to complete, then try again."
        )
        ctx.sources = []
        ctx.confidence_score = 0.0
        ctx.gated = True
        ctx.error = f"ingestion incomplete (status: {status})"
        return _transition(ctx, AgentState.RESPOND)

    ctx.max_iterations = ctx.max_iterations or settings.MAX_ITERATIONS
    return _transition(ctx, AgentState.PLAN)


@_register(AgentState.PLAN)
def _handle_plan(ctx: AgentContext) -> AgentState:
    from app.retrieval.query_expansion import expand_query

    if not ctx.query_variants:
        ctx.query_variants = expand_query(ctx.question)[:3]
    if ctx.iteration == 0:
        ctx.need_structural = _needs_structural_context(ctx.question)
    return _transition(ctx, AgentState.ACT)


@_register(AgentState.ACT)
def _handle_act(ctx: AgentContext) -> AgentState:
    from app.retrieval.hybrid_search import search
    from app.retrieval.reranker import rerank

    batches: list[list[dict[str, Any]]] = []
    for variant in ctx.query_variants:
        try:
            batches.append(search(ctx.repo_id, variant, top_k=20))
        except Exception as exc:
            logger.warning("act_search_failed", variant=variant, error=str(exc))

    merged = _merge_search_results(batches)
    try:
        ctx.chunks = rerank(ctx.question, merged, top_n=8)
    except Exception as exc:
        logger.warning("act_rerank_failed", error=str(exc))
        ctx.chunks = merged[:8]

    for hit in ctx.chunks:
        score = float(hit.get("score", 0.0))
        if score > ctx.best_retrieval_score:
            ctx.best_retrieval_score = score

    if ctx.need_structural and not ctx.graph_context:
        try:
            from app.graph.queries import get_callers, get_callees

            symbol = _extract_symbol(ctx.question)
            if symbol:
                callers = get_callers(ctx.repo_id, symbol)[:5]
                callees = get_callees(ctx.repo_id, symbol)[:5]
                lines = [f"Symbol: {symbol}"]
                if callers:
                    lines.append("Callers: " + ", ".join(c["caller"] for c in callers))
                if callees:
                    lines.append("Callees: " + ", ".join(c["callee"] for c in callees))
                ctx.graph_context = "\n".join(lines)
        except Exception as exc:
            logger.debug("act_graph_context_skipped", error=str(exc))

    return _transition(ctx, AgentState.OBSERVE)


def _extract_symbol(question: str) -> str | None:
    m = re.search(r"`([A-Za-z_][\w.]*)`", question)
    if m:
        return m.group(1).split(".")[-1]
    m = re.search(r"\b([A-Z][A-Za-z0-9_]+)\b", question)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-z_][a-z0-9_]{2,})\b", question)
    return m.group(1) if m else None


@_register(AgentState.OBSERVE)
def _handle_observe(ctx: AgentContext) -> AgentState:
    ctx.assembled_context = context_manager_assemble(
        ctx.chunks,
        ctx.graph_context,
        max_tokens=_DEFAULT_CONTEXT_TOKEN_BUDGET,
    )
    return _transition(ctx, AgentState.DECIDE)


@_register(AgentState.DECIDE)
def _handle_decide(ctx: AgentContext) -> AgentState:
    if ctx.iteration >= ctx.max_iterations:
        ctx.error = "Could not resolve within the iteration limit."
        return _transition(ctx, AgentState.FINALIZE)

    if not ctx.chunks and ctx.iteration >= ctx.max_iterations - 1:
        return _transition(ctx, AgentState.FINALIZE)

    prompt = (
        "You are a strict evidence checker. Given the QUESTION and CONTEXT below, "
        "reply with exactly one word: YES if the context contains enough information "
        "to answer accurately, or NO if another retrieval pass is needed.\n\n"
        f"QUESTION:\n{ctx.question}\n\nCONTEXT:\n{ctx.assembled_context[:3000]}"
    )
    try:
        verdict = _groq_text(
            "Reply only YES or NO.",
            prompt,
            max_tokens=8,
        ).upper()
        ctx.enough_evidence = verdict.startswith("Y")
    except RateLimitError:
        ctx.rate_limited = True
        ctx.answer = (
            "The AI provider is temporarily rate-limited. "
            "Please wait about 30 seconds and try again."
        )
        ctx.gated = True
        return _transition(ctx, AgentState.RESPOND)
    except ProviderError as exc:
        if ctx.iteration == 0:
            ctx.groq_failed = True
            ctx.answer = f"Unable to complete the request: {exc}"
            ctx.gated = True
            return _transition(ctx, AgentState.RESPOND)
        ctx.enough_evidence = True

    if ctx.enough_evidence or ctx.iteration + 1 >= ctx.max_iterations:
        return _transition(ctx, AgentState.FINALIZE)

    ctx.iteration += 1
    return _transition(ctx, AgentState.ACT)


@_register(AgentState.FINALIZE)
def _handle_finalize(ctx: AgentContext) -> AgentState:
    if ctx.max_iterations > 0 and ctx.iteration + 1 >= ctx.max_iterations and not ctx.enough_evidence:
        ctx.gated = True

    system = (
        "You are a codebase onboarding assistant. Answer ONLY using the provided context. "
        "Cite sources inline using backticks: `path/to/file.py:line` or `function_name()`. "
        "If context is insufficient, say what is missing — do not invent file paths."
    )
    user = (
        f"QUESTION:\n{ctx.question}\n\n"
        f"CONTEXT:\n{ctx.assembled_context}\n\n"
        "Provide a concise, well-structured answer with citations."
    )
    try:
        ctx.answer = _groq_text(system, user, max_tokens=_FINALIZE_MAX_TOKENS)
    except RateLimitError:
        ctx.rate_limited = True
        ctx.answer = (
            "The AI provider is temporarily rate-limited. "
            "Please wait about 30 seconds and try again."
        )
        ctx.gated = True
        return _transition(ctx, AgentState.RESPOND)
    except ProviderError as exc:
        ctx.groq_failed = True
        ctx.answer = f"Unable to generate an answer: {exc}"
        ctx.gated = True
        return _transition(ctx, AgentState.RESPOND)

    ctx.sources = _hits_to_sources(ctx.chunks)
    return _transition(ctx, AgentState.VERIFY)


@_register(AgentState.VERIFY)
def _handle_verify(ctx: AgentContext) -> AgentState:
    score, gated, disclaimer = confidence_verify(
        ctx.answer,
        ctx.sources,
        best_retrieval_score=ctx.best_retrieval_score,
    )
    ctx.confidence_score = score
    ctx.gated = gated or ctx.gated
    if disclaimer and ctx.gated:
        ctx.answer = str(ctx.answer or "").rstrip() + str(disclaimer)
    return _transition(ctx, AgentState.RESPOND)


@_register(AgentState.RESPOND)
def _handle_respond(ctx: AgentContext) -> AgentState:
    if not ctx.cache_hit and not ctx.groq_failed and not ctx.rate_limited:
        semantic_cache_store(
            ctx.repo_id,
            ctx.question,
            {
                "answer": ctx.answer,
                "sources": ctx.sources,
                "confidence_score": ctx.confidence_score,
                "gated": ctx.gated,
            },
        )
    return _transition(ctx, AgentState.RESPOND)


def run(
    repo_id: str,
    question: str,
    session_id: str | None = None,
    *,
    chat_history: list[dict[str, Any]] | None = None,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """
    Public entry point for POST /chat — steps through the state machine.

    Returns ``{answer, sources, confidence_score, gated}`` matching the API contract.
    """
    log = logger.bind(repo_id=repo_id, session_id=session_id or "")
    ctx = AgentContext(
        repo_id=repo_id,
        question=question,
        session_id=session_id,
        chat_history=list(chat_history or []),
        max_iterations=max_iterations or settings.MAX_ITERATIONS,
    )

    state = AgentState.INTAKE
    safety = 0
    while safety < 40:
        safety += 1
        if state == AgentState.RESPOND:
            _handle_respond(ctx)
            break
        handler = _STATE_HANDLERS.get(state)
        if handler is None:
            log.error("unknown_agent_state", state=state)
            ctx.answer = "Internal agent error: unknown state."
            ctx.gated = True
            break
        state = handler(ctx)

    result: dict[str, Any] = {
        "answer": ctx.answer,
        "sources": ctx.sources,
        "confidence_score": ctx.confidence_score,
        "gated": ctx.gated,
    }
    if ctx.cache_hit:
        result["cache_hit"] = True
    if ctx.rate_limited:
        result["rate_limited"] = True
    if ctx.timed_out:
        result["timed_out"] = True
    if ctx.error:
        result["error"] = ctx.error
    elif ctx.groq_failed:
        result["error"] = ctx.answer
    if ctx.state_trace:
        result["trace"] = [{"state": s} for s in ctx.state_trace]
    log.info("agent_run_complete", gated=ctx.gated, cache_hit=ctx.cache_hit, states=ctx.state_trace)
    return result


# ---------------------------------------------------------------------------
# Backward-compatible aliases (eval, semantic_cache wrapper, legacy tests)
# ---------------------------------------------------------------------------

def _prefetch_context(question: str, repo_id: str, log: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]], float]:
    """Legacy helper used by semantic_cache refresh — thin retrieval prefetch."""
    from app.agent.retrieval_prefetch import run_prefetch

    def _hits_from_search_result(tool_result: dict[str, Any]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for r in tool_result.get("results", []):
            meta = r.get("metadata") or {}
            hits.append({
                "file_path": meta.get("display_path") or meta.get("file_path") or "",
                "function_name": meta.get("function_name"),
                "start_line": meta.get("start_line"),
                "end_line": meta.get("end_line"),
                "rerank_score": r.get("rerank_score", 0.0),
                "chunk": r.get("chunk") or "",
            })
        return hits

    return run_prefetch(
        question,
        repo_id,
        log,
        hits_from_result=_hits_from_search_result,
        reorder_hits=lambda _q, hits: hits,
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
    """Backward-compatible wrapper around ``run()`` for existing callers."""
    _ = (max_tool_calls, max_total_tokens, context_compression_threshold, request_id, max_wall_seconds)
    if max_iterations is not None:
        result = run(repo_id, question, chat_history=chat_history, max_iterations=max_iterations)
    else:
        result = run(repo_id, question, chat_history=chat_history)

    if "confidence" not in result:
        result["confidence"] = "low" if result.get("gated") else "high"
    return result
