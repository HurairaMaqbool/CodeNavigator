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

# Exact-question replay cache — zero Groq on repeated identical questions (local testing).
_EXACT_QUESTION_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


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
    max_tokens: int | None = None,
) -> str:
    """
    FORWARD STUB — Module #25 ``context_manager.assemble_context(chunks, graph, max_tokens)``.

    Trims merged chunk text to a token budget before DECIDE/FINALIZE Groq calls.
    Chunks are sorted by rerank score (highest first) before truncation.
    """
    token_budget = max_tokens or int(settings.CONTEXT_MAX_TOKENS)
    budget_chars = max(settings.CONTEXT_BUDGET_MIN_CHARS, token_budget * 4)
    ranked = sorted(
        chunks,
        key=lambda h: float(h.get("score", 0.0)),
        reverse=True,
    )
    parts: list[str] = []
    used = 0
    for hit in ranked:
        text = hit.get("chunk") or ""
        if not text:
            continue
        meta = hit.get("chunk_metadata") or {}
        header = meta.get("display_path") or meta.get("file_path") or "chunk"
        block = f"### {header}\n{text}"
        if used + len(block) > budget_chars:
            remaining = budget_chars - used
            if remaining > settings.CONTEXT_TRUNCATE_REMAINING_CHARS:
                parts.append(block[:remaining] + "\n...[truncated]")
            break
        parts.append(block)
        used += len(block)
    if graph_context:
        parts.append(f"### Graph context\n{graph_context[:settings.GRAPH_CONTEXT_MAX_CHARS]}")
    assembled = "\n\n".join(parts) if parts else "(no context retrieved)"
    est_tokens = max(1, len(assembled) // 4)
    logger.info(
        "context_assembled",
        chunk_count=len(ranked),
        chunks_included=len(parts),
        estimated_context_tokens=est_tokens,
        token_budget=token_budget,
    )
    return assembled


def confidence_verify(
    answer: str,
    sources: list[dict[str, Any]],
    *,
    repo_id: str = "",
    best_retrieval_score: float,
    invalid_reference_ratio: float = 0.0,
) -> tuple[float, bool, str]:
    """
    Module #26 VERIFY — delegates to ``evaluate()`` when ``repo_id`` is set.

    Returns ``(confidence_score, gated, optional_disclaimer)``.
    """
    if repo_id:
        from app.agent.confidence import evaluate

        out = evaluate(answer or "", repo_id)
        return out["confidence_score"], out["gated"], ""

    from app.agent.confidence import compute_confidence_score

    score = compute_confidence_score(
        invalid_reference_ratio,
        best_retrieval_score,
        min(len(sources), 3),
    )
    gated = score < settings.MIN_CONFIDENCE_SCORE
    return score, gated, ""


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
    job_id: str | None = None
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    query_variants: list[str] = field(default_factory=list)
    need_structural: bool = False
    chunks: list[dict[str, Any]] = field(default_factory=list)
    graph_context: str = ""
    assembled_context: str = ""
    enough_evidence: bool = False
    answer: str = ""
    structured_claims: list[dict[str, Any]] = field(default_factory=list)
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
    retry_after_s: float | None = None
    groq_calls: int = 0
    timed_out: bool = False
    started_monotonic: float = 0.0


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


def _elapsed_s(ctx: AgentContext) -> float:
    if ctx.started_monotonic <= 0:
        return 0.0
    return time.monotonic() - ctx.started_monotonic


def _wall_clock_exceeded(ctx: AgentContext) -> bool:
    limit = max(10, int(settings.AGENT_MAX_SECONDS))
    return _elapsed_s(ctx) >= limit


def _retrieval_strong_enough(ctx: AgentContext) -> bool:
    if not ctx.chunks:
        return False
    if ctx.best_retrieval_score >= settings.RETRIEVAL_FAST_PATH_SCORE:
        return True
    # Multiple solid hits — skip DECIDE to save a Groq call (TPM budget).
    return len(ctx.chunks) >= 4 and ctx.best_retrieval_score >= 0.18


def _parse_retry_after_s(exc: Exception) -> float | None:
    m = re.search(r"Retry after ([\d.]+)s", str(exc))
    return float(m.group(1)) if m else None


def _apply_provider_failure(ctx: AgentContext, exc: Exception, *, phase: str) -> str:
    """Classify provider errors so router can return 429/504 instead of gated 200."""
    ctx.groq_failed = True
    err = str(exc).lower()
    if isinstance(exc, RateLimitError) or "rate limit" in err:
        ctx.rate_limited = True
        if ctx.retry_after_s is None:
            parsed = _parse_retry_after_s(exc)
            if parsed is not None:
                ctx.retry_after_s = parsed
        wait = int(ctx.retry_after_s or 30)
        return (
            f"The AI provider is temporarily rate-limited. "
            f"Please wait about {wait} seconds and try again."
        )
    if "timed out" in err or "time-to-first-token" in err:
        ctx.timed_out = True
        return (
            "The AI provider was too slow to generate an answer. "
            "Try a more specific question about a class, function, or file."
        )
    return f"Unable to complete the {phase} step: {exc}"


def _exact_question_cache_get(repo_id: str, question: str) -> dict[str, Any] | None:
    key = (repo_id, question.strip().lower())
    entry = _EXACT_QUESTION_CACHE.get(key)
    if not entry:
        return None
    ts, payload = entry
    if time.monotonic() - ts > settings.EXACT_QUESTION_CACHE_TTL_S:
        _EXACT_QUESTION_CACHE.pop(key, None)
        return None
    if payload.get("gated"):
        return None
    logger.info("exact_question_cache_hit", repo_id=repo_id)
    return payload


def _exact_question_cache_put(repo_id: str, question: str, response: dict[str, Any]) -> None:
    if response.get("gated") or response.get("rate_limited"):
        return
    key = (repo_id, question.strip().lower())
    _EXACT_QUESTION_CACHE[key] = (time.monotonic(), response)


def _groq_text(
    system: str,
    user: str,
    *,
    max_tokens: int = 256,
    purpose: str = "text",
    model: str | None = None,
    wall_clock_timeout_s: float | None = None,
    ctx: AgentContext | None = None,
) -> str:
    """
    Single controlled Groq text call with streaming.

    Exactly one SDK attempt per invocation; at most one extra attempt on 429
    with ``retry-after`` backoff — no stacked SDK/tenacity retries.
    """
    llm = get_llm_client()
    if not hasattr(llm, "stream_text"):
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

    est_tokens = max(1, (len(system) + len(user)) // 4)
    use_model = model or settings.LLM_MODEL
    wall = wall_clock_timeout_s or float(settings.GROQ_FINALIZE_TIMEOUT_S)

    for attempt in range(max(1, int(settings.GROQ_LLM_RATE_LIMIT_ATTEMPTS))):
        logger.info(
            "loop_llm_call_start",
            purpose=purpose,
            attempt=attempt + 1,
            model=use_model,
            estimated_input_tokens=est_tokens,
            max_tokens=max_tokens,
            wall_clock_timeout_s=wall,
        )
        t0 = time.monotonic()
        try:
            out = llm.stream_text(
                system,
                user,
                max_tokens=max_tokens,
                model=use_model,
                purpose=purpose,
                wall_clock_timeout_s=wall,
                ttft_timeout_s=float(settings.GROQ_TTFT_TIMEOUT_S),
            )
            if isinstance(out, tuple) and len(out) == 2:
                text, meta = out
            else:
                text = out if isinstance(out, str) else ""
                meta = {"sdk_attempts": 1}
            logger.info(
                "loop_llm_call_complete",
                purpose=purpose,
                attempt=attempt + 1,
                elapsed_s=round(time.monotonic() - t0, 3),
                sdk_attempts=meta.get("sdk_attempts", 1),
                estimated_input_tokens=est_tokens,
                success=True,
            )
            if ctx is not None:
                ctx.groq_calls += 1
            return text
        except RateLimitError as exc:
            elapsed = time.monotonic() - t0
            retry_s = _parse_retry_after_s(exc)
            if ctx is not None and retry_s is not None:
                ctx.retry_after_s = retry_s
            logger.warning(
                "loop_llm_rate_limited",
                purpose=purpose,
                attempt=attempt + 1,
                elapsed_s=round(elapsed, 3),
                error=str(exc),
            )
            max_attempts = max(1, int(settings.GROQ_LLM_RATE_LIMIT_ATTEMPTS))
            if attempt + 1 < max_attempts and (retry_s is None or retry_s <= 10.0):
                delay = retry_s if retry_s is not None else 5.0
                time.sleep(min(delay, settings.LLM_RATE_LIMIT_MAX_BACKOFF_S))
                continue
            raise
        except ProviderError as exc:
            logger.warning(
                "loop_llm_provider_error",
                purpose=purpose,
                attempt=attempt + 1,
                elapsed_s=round(time.monotonic() - t0, 3),
                error=str(exc),
            )
            raise

    raise ProviderError("Groq call failed after bounded retries")


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
            "lines": s.get("lines") or (f"{start_line}-{end_line}" if start_line != end_line else str(start_line)),
            "start_line": start_line,
            "end_line": end_line,
        })
    return out


def _chunks_to_repair_hits(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten retrieval chunks into the shape expected by ``citation_repair``."""
    hits: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.get("chunk_metadata") or {}
        path = meta.get("display_path") or meta.get("file_path") or ""
        if not path:
            continue
        hits.append({
            "file_path": path,
            "function_name": meta.get("function_name") or "",
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "chunk": chunk.get("chunk") or "",
        })
    return hits


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
    # Exact replay cache (zero Groq) — before semantic cache embedding call.
    if not ctx.chat_history:
        exact = _exact_question_cache_get(ctx.repo_id, ctx.question)
        if exact:
            ctx.answer = exact["answer"]
            ctx.sources = exact.get("sources", [])
            ctx.confidence_score = float(exact.get("confidence_score", 0.0))
            ctx.gated = bool(exact.get("gated", False))
            ctx.cache_hit = True
            return _transition(ctx, AgentState.RESPOND)

    # Semantic cache (embedding lookup, no Groq on hit).
    if not ctx.chat_history:
        cached = semantic_cache_lookup(ctx.repo_id, ctx.question)
        if cached and not cached.get("gated"):
            ctx.answer = cached["answer"]
            ctx.sources = cached.get("sources", [])
            ctx.confidence_score = float(cached.get("confidence_score", 0.0))
            ctx.gated = bool(cached.get("gated", False))
            ctx.cache_hit = True
            return _transition(ctx, AgentState.RESPOND)

    from app.ingestion.repo_readiness import evaluate_chat_readiness

    gate_id = ctx.job_id or ctx.repo_id
    readiness = evaluate_chat_readiness(gate_id, asset_repo_id=ctx.repo_id)
    if not readiness.ready:
        ctx.answer = readiness.block_message
        ctx.sources = []
        ctx.confidence_score = 0.0
        ctx.gated = True
        ctx.error = readiness.block_reason or "ingestion incomplete"
        return _transition(ctx, AgentState.RESPOND)

    ctx.max_iterations = ctx.max_iterations or settings.MAX_ITERATIONS
    return _transition(ctx, AgentState.PLAN)


@_register(AgentState.PLAN)
def _handle_plan(ctx: AgentContext) -> AgentState:
    from app.retrieval.query_expansion import expand_query

    if not ctx.query_variants:
        if settings.QUERY_EXPANSION_ENABLED:
            variants = expand_query(ctx.question)
        else:
            variants = [ctx.question]
        cap = max(1, int(settings.MAX_QUERY_VARIANTS))
        ctx.query_variants = variants[:cap]
    if ctx.iteration == 0:
        ctx.need_structural = _needs_structural_context(ctx.question)
    return _transition(ctx, AgentState.ACT)


@_register(AgentState.ACT)
def _handle_act(ctx: AgentContext) -> AgentState:
    from app.retrieval.hybrid_search import search
    from app.retrieval.reranker import rerank

    batches: list[list[dict[str, Any]]] = []
    variants = ctx.query_variants if ctx.iteration == 0 else ctx.query_variants[:1]
    for variant in variants:
        try:
            batches.append(search(ctx.repo_id, variant, top_k=settings.HYBRID_SEARCH_TOP_K))
        except Exception as exc:
            logger.warning("act_search_failed", variant=variant, error=str(exc))

    merged = _merge_search_results(batches)
    try:
        ctx.chunks = rerank(ctx.question, merged, top_n=settings.RERANK_TOP_N)
    except Exception as exc:
        logger.warning("act_rerank_failed", error=str(exc))
        ctx.chunks = merged[: settings.RERANK_TOP_N]

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
        max_tokens=int(settings.CONTEXT_MAX_TOKENS),
    )
    return _transition(ctx, AgentState.DECIDE)


@_register(AgentState.DECIDE)
def _handle_decide(ctx: AgentContext) -> AgentState:
    if ctx.iteration >= ctx.max_iterations:
        ctx.error = "Could not resolve within the iteration limit."
        return _transition(ctx, AgentState.FINALIZE)

    if not ctx.chunks and ctx.iteration >= ctx.max_iterations - 1:
        return _transition(ctx, AgentState.FINALIZE)

    # Fast path: strong retrieval on a single-variant search — skip DECIDE LLM.
    if (
        ctx.iteration == 0
        and len(ctx.query_variants) <= 1
        and _retrieval_strong_enough(ctx)
    ):
        ctx.enough_evidence = True
        return _transition(ctx, AgentState.FINALIZE)

    if _wall_clock_exceeded(ctx):
        ctx.timed_out = True
        ctx.enough_evidence = bool(ctx.chunks)
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
            max_tokens=settings.DECIDE_MAX_TOKENS,
            purpose="decide",
            model=settings.DECIDE_LLM_MODEL,
            wall_clock_timeout_s=float(settings.GROQ_DECIDE_TIMEOUT_S),
            ctx=ctx,
        ).upper()
        ctx.enough_evidence = verdict.startswith("Y")
    except RateLimitError as exc:
        ctx.answer = _apply_provider_failure(ctx, exc, phase="decide")
        ctx.gated = True
        return _transition(ctx, AgentState.RESPOND)
    except ProviderError as exc:
        if ctx.iteration == 0:
            ctx.answer = _apply_provider_failure(ctx, exc, phase="decide")
            ctx.gated = True
            return _transition(ctx, AgentState.RESPOND)
        ctx.enough_evidence = True

    if ctx.enough_evidence or ctx.iteration + 1 >= ctx.max_iterations:
        return _transition(ctx, AgentState.FINALIZE)

    ctx.iteration += 1
    return _transition(ctx, AgentState.ACT)


@_register(AgentState.FINALIZE)
def _handle_finalize(ctx: AgentContext) -> AgentState:
    from app.agent.prompts.finalize_prompt import finalize_prompt, finalize_system_prompt

    allowed_paths = sorted({
        (c.get("chunk_metadata") or {}).get("display_path")
        or (c.get("chunk_metadata") or {}).get("file_path")
        for c in ctx.chunks
    } - {None, ""})
    assembled = ctx.assembled_context
    if allowed_paths:
        path_lines = "\n".join(f"- `{p}`" for p in allowed_paths[:25])
        assembled = (
            f"{assembled}\n\n"
            "INDEXED FILES YOU MAY CITE (use exact paths with line numbers from context):\n"
            f"{path_lines}"
        )

    system = finalize_system_prompt()
    user = finalize_prompt({
        "question": ctx.question,
        "assembled_context": assembled,
        "graph_context": ctx.graph_context,
    })
    try:
        raw = _groq_text(
            system,
            user,
            max_tokens=settings.FINALIZE_MAX_TOKENS,
            purpose="finalize",
            model=settings.LLM_MODEL,
            wall_clock_timeout_s=float(settings.GROQ_FINALIZE_TIMEOUT_S),
            ctx=ctx,
        )
    except RateLimitError as exc:
        ctx.answer = _apply_provider_failure(ctx, exc, phase="finalize")
        ctx.gated = True
        return _transition(ctx, AgentState.RESPOND)
    except ProviderError as exc:
        ctx.answer = _apply_provider_failure(ctx, exc, phase="finalize")
        ctx.gated = True
        return _transition(ctx, AgentState.RESPOND)

    from app.agent.grounding import claims_to_sources, parse_finalize_json, render_claims_markdown

    claims = parse_finalize_json(raw)
    if claims:
        ctx.structured_claims = claims
        ctx.answer = render_claims_markdown(claims)
        ctx.sources = claims_to_sources(claims) or _hits_to_sources(ctx.chunks)
    else:
        logger.warning("finalize_json_empty_fallback_to_prose", repo_id=ctx.repo_id)
        ctx.structured_claims = []
        ctx.answer = raw
        ctx.sources = _hits_to_sources(ctx.chunks)

    return _transition(ctx, AgentState.VERIFY)


@_register(AgentState.VERIFY)
def _handle_verify(ctx: AgentContext) -> AgentState:
    from app.agent.citation_repair import repair_answer_citations
    from app.agent.claim_verification import verify_claims_batch
    from app.agent.confidence import (
        GATED_FALLBACK_MESSAGE,
        evaluate,
        evaluate_structured_claims,
        has_placeholder_citations,
        validate_sources,
    )
    from app.agent.response_firewall import sanitize_user_answer

    if ctx.structured_claims:
        # Repair structured claims citations first using symbol resolution
        try:
            from app.agent.citation_repair import _resolve_citation_lines, _hits_by_path
            by_path = _hits_by_path(_chunks_to_repair_hits(ctx.chunks))
            for claim in ctx.structured_claims:
                cit = claim.get("citation")
                if cit and cit.get("file_path"):
                    sent = claim.get("claim") or ""
                    correct = _resolve_citation_lines(ctx.repo_id, cit["file_path"], sent, by_path)
                    if correct:
                        if "-" in correct:
                            a, b = correct.split("-", 1)
                            cit["start_line"] = int(a)
                            cit["end_line"] = int(b)
                        else:
                            cit["start_line"] = cit["end_line"] = int(correct)
        except Exception as exc:
            logger.warning("structured_claims_repair_failed", error=str(exc))

        from app.agent.confidence import path_key
        import traceback

        allowed_paths = {
            path_key(str(
                (c.get("chunk_metadata") or {}).get("display_path")
                or (c.get("chunk_metadata") or {}).get("file_path")
                or ""
            ))
            for c in ctx.chunks
        } - {""}
        try:
            verification = verify_claims_batch(
                ctx.structured_claims,
                ctx.repo_id,
                retrieval_hits=ctx.chunks,
                allowed_paths=allowed_paths,
            )
            if verification.get("verification_error"):
                logger.error(
                    "verify_system_error",
                    repo_id=ctx.repo_id,
                    phase="claim_batch",
                    error=verification.get("error"),
                )
                from app.agent.confidence import VERIFY_SYSTEM_ERROR_MESSAGE

                ctx.confidence_score = 0.0
                ctx.gated = True
                ctx.answer = VERIFY_SYSTEM_ERROR_MESSAGE
                ctx.sources = []
                return _transition(ctx, AgentState.RESPOND)

            result = evaluate_structured_claims(
                ctx.structured_claims,
                ctx.answer or "",
                ctx.repo_id,
                verification,
            )
        except Exception as exc:
            logger.error(
                "verify_system_error",
                repo_id=ctx.repo_id,
                phase="structured_verify",
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            from app.agent.confidence import VERIFY_SYSTEM_ERROR_MESSAGE

            ctx.confidence_score = 0.0
            ctx.gated = True
            ctx.answer = VERIFY_SYSTEM_ERROR_MESSAGE
            ctx.sources = []
            return _transition(ctx, AgentState.RESPOND)

        if result.get("verification_error"):
            logger.error(
                "verify_system_error",
                repo_id=ctx.repo_id,
                phase="evaluate_structured",
            )
            ctx.confidence_score = 0.0
            ctx.gated = True
            ctx.answer = result["answer"]
            ctx.sources = []
            return _transition(ctx, AgentState.RESPOND)

        ctx.confidence_score = float(result["confidence_score"])
        ctx.gated = bool(result["gated"])
        if ctx.gated:
            logger.warning(
                "verify_gated_structured",
                repo_id=ctx.repo_id,
                score=ctx.confidence_score,
                claim_count=len(ctx.structured_claims),
                verified_count=verification.get("verified_count"),
                methods=[r.get("method") for r in verification.get("results") or []],
                rejection_reason=result.get("rejection_reason", "claims_unsupported"),
            )
            ctx.answer = result["answer"]
            ctx.sources = []
        else:
            ctx.answer = sanitize_user_answer(result["answer"])
            ctx.sources = validate_sources(ctx.sources, ctx.repo_id)
            if ctx.answer and len(ctx.answer.split()) > 110:
                import re
                sentences = re.split(r'(?<=[.!?])\s+', ctx.answer)
                truncated_sentences = []
                words_count = 0
                for sent in sentences:
                    sent_words_len = len(sent.split())
                    if not truncated_sentences or words_count + sent_words_len <= 110:
                        truncated_sentences.append(sent)
                        words_count += sent_words_len
                    else:
                        break
                if truncated_sentences:
                    ctx.answer = " ".join(truncated_sentences)
                else:
                    ctx.answer = " ".join(ctx.answer.split()[:110]) + "..."
        return _transition(ctx, AgentState.RESPOND)

    repair_hits = _chunks_to_repair_hits(ctx.chunks)
    repaired = repair_answer_citations(
        ctx.answer or "",
        repair_hits,
        repo_id=ctx.repo_id,
        question=ctx.question,
    )
    if has_placeholder_citations(ctx.answer or ""):
        result = {
            "answer": GATED_FALLBACK_MESSAGE,
            "confidence_score": 0.0,
            "gated": True,
        }
    elif not repaired.strip():
        result = {
            "answer": GATED_FALLBACK_MESSAGE,
            "confidence_score": 0.0,
            "gated": True,
        }
    else:
        result = evaluate(repaired, ctx.repo_id)

    # Source-backed fallback: retrieval was good but inline cites failed VERIFY.
    if (
        result.get("gated")
        and not has_placeholder_citations(ctx.answer or "")
        and not has_placeholder_citations(repaired)
    ):
        valid_sources = validate_sources(ctx.sources, ctx.repo_id)
        clean = sanitize_user_answer(repaired)
        if valid_sources and clean and len(clean) >= 40:
            result = {
                "answer": clean,
                "confidence_score": max(
                    float(result.get("confidence_score", 0.0)),
                    float(settings.MIN_CONFIDENCE_SCORE),
                ),
                "gated": False,
            }
            ctx.sources = valid_sources

    ctx.confidence_score = float(result["confidence_score"])
    ctx.gated = bool(result["gated"])

    if ctx.gated:
        ctx.answer = result["answer"]
        ctx.sources = []
    else:
        ctx.answer = result["answer"]
        ctx.sources = validate_sources(ctx.sources, ctx.repo_id)
        if ctx.answer and len(ctx.answer.split()) > 110:
            import re
            sentences = re.split(r'(?<=[.!?])\s+', ctx.answer)
            truncated_sentences = []
            words_count = 0
            for sent in sentences:
                sent_words_len = len(sent.split())
                if not truncated_sentences or words_count + sent_words_len <= 110:
                    truncated_sentences.append(sent)
                    words_count += sent_words_len
                else:
                    break
            if truncated_sentences:
                ctx.answer = " ".join(truncated_sentences)
            else:
                ctx.answer = " ".join(ctx.answer.split()[:110]) + "..."
    return _transition(ctx, AgentState.RESPOND)


@_register(AgentState.RESPOND)
def _handle_respond(ctx: AgentContext) -> AgentState:
    if not ctx.cache_hit and not ctx.groq_failed and not ctx.rate_limited and not ctx.gated:
        payload = {
            "answer": ctx.answer,
            "sources": ctx.sources,
            "confidence_score": ctx.confidence_score,
            "gated": ctx.gated,
        }
        semantic_cache_store(ctx.repo_id, ctx.question, payload)
        if not ctx.chat_history:
            _exact_question_cache_put(ctx.repo_id, ctx.question, payload)
    return AgentState.RESPOND


def run(
    repo_id: str,
    question: str,
    session_id: str | None = None,
    *,
    job_id: str | None = None,
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
        job_id=job_id or repo_id,
        question=question,
        session_id=session_id,
        chat_history=list(chat_history or []),
        max_iterations=max_iterations or settings.MAX_ITERATIONS,
        started_monotonic=time.monotonic(),
    )

    state = AgentState.INTAKE
    safety = 0
    while safety < 40:
        safety += 1
        if _wall_clock_exceeded(ctx) and state not in (
            AgentState.FINALIZE,
            AgentState.VERIFY,
            AgentState.RESPOND,
        ):
            ctx.timed_out = True
            if ctx.chunks and state != AgentState.FINALIZE:
                state = AgentState.FINALIZE
                continue
            if not ctx.answer:
                ctx.answer = (
                    "The request took too long to complete. "
                    "Please try a more specific question about a class, function, or file."
                )
            ctx.gated = True
            state = AgentState.RESPOND
            continue
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
        if ctx.retry_after_s is not None:
            result["retry_after_s"] = ctx.retry_after_s
    if ctx.timed_out:
        result["timed_out"] = True
    result["groq_calls"] = ctx.groq_calls
    if ctx.error:
        result["error"] = ctx.error
    elif ctx.groq_failed:
        result["error"] = ctx.answer
    if ctx.state_trace:
        result["trace"] = [{"state": s} for s in ctx.state_trace]
    log.info("agent_run_complete", gated=ctx.gated, cache_hit=ctx.cache_hit, groq_calls=ctx.groq_calls, states=ctx.state_trace)
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
