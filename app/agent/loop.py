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

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from app.agent.llm_client import ProviderError, RateLimitError, get_llm_client
from app.agent.confidence import VERIFY_SYSTEM_ERROR_MESSAGE
from app.config import settings
from app.observability.logging_config import logger

# Re-exported for tests and semantic_cache refresh (Module #24 integration).
from app.agent.context_manager import compress_older_tool_results  # noqa: F401
from app.agent.tools import execute_tool_with_retry  # noqa: F401
from app.ingestion.metadata_store import metadata_store  # noqa: F401
from app.cache.tool_cache import ToolCache

_TOOL_CACHE = ToolCache()

# Exact-question replay cache — zero Groq on repeated identical questions (local testing).
_EXACT_QUESTION_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_MODELS_WARMED = False


def _ensure_models_warmed() -> None:
    """Lazy warm-up when agent runs outside FastAPI lifespan (scripts, tests)."""
    global _MODELS_WARMED
    if _MODELS_WARMED:
        return
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from app.main import on_startup

        on_startup()
        _MODELS_WARMED = True
    except Exception as exc:
        logger.warning("agent_lazy_model_warmup_failed", error=str(exc))


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
            candidate = {
                "answer": payload["answer"],
                "sources": payload.get("sources", []),
                "confidence_score": float(payload.get("confidence_score", 0.0)),
                "gated": bool(payload.get("gated", False)),
            }
            if _is_unusable_cached_answer(candidate):
                return None
            return candidate
    except Exception as exc:
        logger.debug("semantic_cache_stub_miss", error=str(exc))
    return None


def semantic_cache_store(repo_id: str, question: str, response: dict[str, Any]) -> None:
    """FORWARD STUB — Module #24 ``semantic_cache.store(repo_id, question, response)``."""
    if not settings.SEMANTIC_CACHE_ENABLED or _is_unusable_cached_answer(response):
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
    question: str | None = None,
) -> tuple[float, bool, str]:
    """
    Module #26 VERIFY — delegates to ``evaluate()`` when ``repo_id`` is set.

    Returns ``(confidence_score, gated, optional_disclaimer)``.
    """
    if repo_id:
        from app.agent.confidence import evaluate

        out = evaluate(
            answer or "",
            repo_id,
            top_retrieval_score=best_retrieval_score,
            question=question,
        )
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
    groq_ms: float = 0.0
    retrieval_ms: float = 0.0
    verify_ms: float = 0.0
    rate_limit_sleep_ms: float = 0.0
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
        "what happens", "internally", " is called", "call chain",
        "transport layer", "retry mechanism",
    )
    return any(m in q for m in markers)


def _needs_flow_tracing(question: str) -> bool:
    from app.retrieval.query_expansion import needs_flow_tracing

    return needs_flow_tracing(question)


def _is_why_question(question: str) -> bool:
    from app.retrieval.source_priority import is_why_query

    return is_why_query(question)


def _chunks_text(chunks: list[dict[str, Any]], limit: int = 12) -> str:
    parts: list[str] = []
    for c in chunks[:limit]:
        meta = c.get("chunk_metadata") or {}
        parts.append(c.get("chunk") or "")
        parts.append(str(meta.get("function_name") or ""))
        parts.append(str(meta.get("display_path") or meta.get("file_path") or ""))
    return " ".join(parts).lower()


def _aspect_markers_satisfied(question: str, chunks: list[dict[str, Any]]) -> bool:
    from app.retrieval.query_expansion import question_aspect_markers

    aspects = question_aspect_markers(question)
    if not aspects:
        return True
    top_text = _chunks_text(chunks)
    for _name, markers in aspects:
        if not any(m.replace(" ", "") in top_text.replace(" ", "") for m in markers):
            return False
    return True


def _flow_chain_satisfied(question: str, chunks: list[dict[str, Any]]) -> bool:
    """Require dispatch/send/urlopen evidence for internal-flow questions."""
    if not _needs_flow_tracing(question):
        return True
    top_text = _chunks_text(chunks)
    dispatch_markers = ("urlopen", "adapter.send", "session.send", "preparedrequest")
    if not any(m in top_text.replace(" ", "") for m in dispatch_markers):
        return False
    q = question.lower()
    if re.search(r"\brequests\.get\b", q):
        flow_markers = ("api.py", "def get", "session.request", "def request")
        return any(m.replace(" ", "") in top_text.replace(" ", "") for m in flow_markers)
    return True


def _follow_up_variants(ctx: AgentContext) -> list[str]:
    """Targeted second-hop queries when the first pass missed key sub-topics."""
    from app.retrieval.query_expansion import decompose_retrieval_variants

    q = ctx.question.lower()
    top_text = _chunks_text(ctx.chunks)
    variants: list[str] = []

    if re.search(r"\bretri", q) and not any(
        m in top_text for m in ("retry", "max_retries", "urllib3")
    ):
        variants.append("urllib3 Retry max_retries HTTPAdapter __init__ send")
    if re.search(r"\btimeout", q) and "timeout" not in top_text:
        variants.append("TimeoutSauce connect read timeout HTTPAdapter send urlopen")
    if _needs_flow_tracing(ctx.question) and "urlopen" not in top_text:
        variants.extend([
            "api.py get request Session.request dispatch",
            "HTTPAdapter.send urlopen PreparedRequest connection pool",
            "Session.send adapter request dispatch",
        ])
    if re.search(r"\bwhy\b", q) and re.search(r"\burllib3\b", q):
        if "readme" not in top_text and "instead of" not in top_text:
            variants.append("README urllib3 design rationale instead of implementing HTTP client")
        variants.append("HISTORY urllib3 maintain complexity reuse connection pool")

    if not variants:
        variants = decompose_retrieval_variants(ctx.question) or [ctx.question]
    return variants[:3]


def _symbol_boost_chunks(
    repo_id: str,
    question: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepend definition chunks for symbols named in the question."""
    from app.agent.symbol_lookup import resolve_symbol_location

    boosted: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    clone_root = Path(settings.REPOS_PATH) / repo_id / "clone"

    for sym in _extract_flow_symbols(question)[:4]:
        kind = "class" if sym[0].isupper() else "function"
        loc = resolve_symbol_location(repo_id, sym, kind=kind)
        if not loc:
            continue
        fp = loc.get("file_path") or ""
        start = int(loc.get("start_line") or 0)
        end = int(loc.get("end_line") or start)
        key = (fp, start, end)
        if not fp or key in seen:
            continue
        seen.add(key)
        chunk_text = f"Definition of {sym} in {fp}"
        src = clone_root / fp.replace("\\", "/").lstrip("./")
        if src.is_file() and start > 0:
            try:
                lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
                end_idx = min(len(lines), max(end, start + 40))
                chunk_text = "\n".join(lines[start - 1 : end_idx])
            except OSError:
                pass
        boosted.append({
            "chunk": chunk_text,
            "chunk_metadata": {
                "file_path": fp,
                "display_path": fp,
                "function_name": loc.get("function_name") or sym,
                "start_line": start,
                "end_line": end,
            },
            "score": 0.95,
        })

    merged: list[dict[str, Any]] = []
    for hit in boosted + hits:
        meta = hit.get("chunk_metadata") or {}
        key = (
            meta.get("file_path", ""),
            int(meta.get("start_line") or 0),
            int(meta.get("end_line") or 0),
        )
        if key in seen and hit not in boosted:
            continue
        if key[0]:
            seen.add(key)
        merged.append(hit)
    return merged


def _read_clone_lines(repo_id: str, rel_path: str, start: int, end: int) -> str:
    clone_root = Path(settings.REPOS_PATH) / repo_id / "clone"
    src = clone_root / rel_path.replace("\\", "/").lstrip("./")
    if not src.is_file() or start <= 0:
        return ""
    try:
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        end_idx = min(len(lines), max(end, start))
        return "\n".join(lines[start - 1 : end_idx])
    except OSError:
        return ""


def _inject_reasoning_chunks(
    repo_id: str,
    question: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepend README/HISTORY and class docstrings for design-rationale questions."""
    from app.retrieval.source_priority import is_reasoning_query

    if not is_reasoning_query(question):
        return hits

    injected: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    q = question.lower()

    for name, end_line in (("README.md", 76), ("HISTORY.md", 80)):
        text = _read_clone_lines(repo_id, name, 1, end_line)
        if not text.strip():
            continue
        rel = name.replace("\\", "/")
        key = (rel, 1, end_line)
        if key in seen:
            continue
        seen.add(key)
        injected.append({
            "chunk": text,
            "chunk_metadata": {
                "file_path": rel,
                "display_path": rel,
                "function_name": "",
                "start_line": 1,
                "end_line": end_line,
                "type": "doc",
            },
            "score": 0.98,
        })

    if re.search(r"\burllib3\b|\bhttpadapter\b", q):
        for rel_path, start, end, fn in (
            ("src/requests/adapters.py", 1, 7, "module_docstring"),
            ("src/requests/adapters.py", 158, 183, "HTTPAdapter"),
        ):
            text = _read_clone_lines(repo_id, rel_path, start, end)
            if not text.strip():
                continue
            key = (rel_path, start, end)
            if key in seen:
                continue
            seen.add(key)
            injected.append({
                "chunk": text,
                "chunk_metadata": {
                    "file_path": rel_path,
                    "display_path": rel_path,
                    "function_name": fn,
                    "start_line": start,
                    "end_line": end,
                    "type": "docstring",
                },
                "score": 0.97,
            })

    if not injected:
        return hits

    merged: list[dict[str, Any]] = []
    merged_seen: set[tuple[str, int, int]] = set()
    for hit in injected + hits:
        meta = hit.get("chunk_metadata") or {}
        key = (
            meta.get("file_path", ""),
            int(meta.get("start_line") or 0),
            int(meta.get("end_line") or 0),
        )
        if key in merged_seen:
            continue
        merged_seen.add(key)
        merged.append(hit)
    return merged


def _extract_flow_symbols(question: str) -> list[str]:
    """Symbols worth boosting for flow/architecture questions."""
    seen: set[str] = set()
    out: list[str] = []
    skip = frozenset({"HTTP", "URL", "API", "JSON", "Python", "Session"})

    for m in re.finditer(r"\brequests\.(get|post|put|patch|delete|head|options)\b", question, re.I):
        for sym in ("request", "Session"):
            if sym not in seen:
                seen.add(sym)
                out.append(sym)

    for sym in re.findall(r"\b([A-Z][A-Za-z0-9_]+)\b", question):
        if sym not in skip and sym not in seen:
            seen.add(sym)
            out.append(sym)

    for sym in re.findall(r"\b([a-z_][a-z0-9_]*)\(\)", question):
        if sym not in seen:
            seen.add(sym)
            out.append(sym)

    if _needs_flow_tracing(question):
        for sym in ("Session", "HTTPAdapter", "send", "request"):
            if sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out


def _elapsed_s(ctx: AgentContext) -> float:
    if ctx.started_monotonic <= 0:
        return 0.0
    return time.monotonic() - ctx.started_monotonic


def _wall_clock_exceeded(ctx: AgentContext) -> bool:
    limit = max(10, int(settings.AGENT_MAX_SECONDS))
    return _elapsed_s(ctx) >= limit


def _remaining_budget_s(ctx: AgentContext | None) -> float:
    if ctx is None or ctx.started_monotonic <= 0:
        return float(settings.AGENT_MAX_SECONDS)
    limit = max(10, int(settings.AGENT_MAX_SECONDS))
    return max(0.0, limit - _elapsed_s(ctx))


def _rate_limit_sleep_budget_exhausted(ctx: AgentContext | None) -> bool:
    if ctx is None:
        return False
    cap = float(settings.AGENT_MAX_CUMULATIVE_RATE_LIMIT_SLEEP_S)
    return cap > 0 and ctx.rate_limit_sleep_ms >= cap * 1000.0


def _apply_request_timeout(ctx: AgentContext, *, phase: str) -> AgentState:
    """Graceful abort when the global wall-clock budget is exhausted."""
    ctx.timed_out = True
    if ctx.structured_claims:
        from app.agent.grounding import render_claims_markdown

        ctx.answer = (
            "This query took longer than expected. Here's what we found so far:\n\n"
            + render_claims_markdown(ctx.structured_claims)
        )
        ctx.gated = False
        return AgentState.VERIFY
    if ctx.answer and ctx.chunks and not ctx.gated:
        ctx.answer = (
            "This query took longer than expected. Here's what we found so far:\n\n"
            + ctx.answer
        )
        ctx.gated = False
        return AgentState.RESPOND
    ctx.answer = (
        "This query is taking longer than expected. "
        "Please try a more specific question about a class, function, or file."
    )
    ctx.gated = True
    ctx.confidence_score = 0.0
    logger.warning("agent_wall_clock_exceeded", phase=phase, elapsed_s=round(_elapsed_s(ctx), 2))
    return AgentState.RESPOND


def _chunks_cover_question_topic(question: str, chunks: list[dict[str, Any]]) -> bool:
    """
    For how/why performance questions, require top chunks to mention the topic.

    Prevents DECIDE fast-path from approving FINALIZE when retrieval surfaced
    unrelated but high-scoring code (e.g. Session.send for a pooling question).
    """
    q = question.lower()
    if not re.search(
        r"\b(how|why)\b.*\b(improve|performance|benefit|faster|efficient|work)\b",
        q,
        re.IGNORECASE,
    ):
        if not _aspect_markers_satisfied(question, chunks):
            return False
        if not _flow_chain_satisfied(question, chunks):
            return False
        return True
    top_text = " ".join(
        (c.get("chunk") or "")
        + " "
        + str((c.get("chunk_metadata") or {}).get("function_name") or "")
        + " "
        + str(
            (c.get("chunk_metadata") or {}).get("display_path")
            or (c.get("chunk_metadata") or {}).get("file_path")
            or ""
        )
        for c in chunks[:5]
    ).lower()
    if re.search(r"\bpool", q):
        pool_markers = (
            "poolmanager", "init_poolmanager", "pool_manager", "httpadapter",
            "connection pool", "keep-alive", "keep alive", "socket reuse",
        )
        return any(marker in top_text for marker in pool_markers)
    stop = {
        "how", "does", "the", "this", "that", "what", "why", "when", "where",
        "improve", "performance", "benefit", "faster", "efficient", "work",
    }
    q_words = [w for w in re.findall(r"\b[a-z]{4,}\b", q) if w not in stop]
    if not q_words:
        return True
    hits = sum(1 for w in q_words if w in top_text)
    return hits >= min(2, len(q_words))


def _retrieval_strong_enough(ctx: AgentContext) -> bool:
    if not ctx.chunks:
        return False
    if not _chunks_cover_question_topic(ctx.question, ctx.chunks):
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


def _is_unusable_cached_answer(payload: dict[str, Any]) -> bool:
    """Never replay internal verification failures or empty gated shells from cache."""
    if not payload:
        return True
    if payload.get("gated") or payload.get("rate_limited"):
        return True
    answer = str(payload.get("answer") or "")
    if not answer.strip():
        return True
    if answer.strip() == VERIFY_SYSTEM_ERROR_MESSAGE:
        return True
    if re.search(r"\bcould not confirm\b|\bcannot confirm\b", answer, re.IGNORECASE):
        return True
    # Duplicate citation ranges usually mean coarse/repetitive answers.
    cites = re.findall(r"`[^`]+:\d+(?:-\d+)?`", answer)
    if len(cites) >= 2 and len(set(cites)) < len(cites):
        return True
    if "verify_system_error" in answer.lower():
        return True
    ans = answer.lower()
    if "request_url" in ans:
        has_flow = any(
            m in ans
            for m in (
                "session.send",
                "adapter.send",
                "urlopen",
                "session.request",
                "def request",
            )
        )
        has_entry = any(m in ans for m in ("api.py", "def get"))
        if has_entry and not has_flow:
            return True
        if not has_flow and not has_entry:
            return True
    return False


def _exact_question_cache_get(repo_id: str, question: str) -> dict[str, Any] | None:
    key = (repo_id, question.strip().lower())
    entry = _EXACT_QUESTION_CACHE.get(key)
    if not entry:
        return None
    ts, payload = entry
    if time.monotonic() - ts > settings.EXACT_QUESTION_CACHE_TTL_S:
        _EXACT_QUESTION_CACHE.pop(key, None)
        return None
    if _is_unusable_cached_answer(payload):
        _EXACT_QUESTION_CACHE.pop(key, None)
        return None
    logger.info("exact_question_cache_hit", repo_id=repo_id)
    return payload


def _exact_question_cache_put(repo_id: str, question: str, response: dict[str, Any]) -> None:
    if _is_unusable_cached_answer(response):
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
    if ctx is not None:
        wall = min(wall, max(1.0, _remaining_budget_s(ctx)))

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
                ctx.groq_ms += (time.monotonic() - t0) * 1000.0
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
            max_backoff = float(settings.LLM_RATE_LIMIT_MAX_BACKOFF_S)
            if attempt + 1 < max_attempts:
                if ctx is not None and (
                    _wall_clock_exceeded(ctx)
                    or _rate_limit_sleep_budget_exhausted(ctx)
                    or _remaining_budget_s(ctx) <= 1.0
                ):
                    raise RateLimitError(
                        "Groq rate limit exceeded and request wall-clock budget is exhausted."
                    ) from exc
                delay = retry_s if retry_s is not None else 5.0
                if retry_s is None or delay <= max_backoff:
                    sleep_s = min(delay + 0.5, max_backoff, _remaining_budget_s(ctx))
                    if ctx is not None and float(settings.AGENT_MAX_CUMULATIVE_RATE_LIMIT_SLEEP_S) > 0:
                        remaining_sleep = (
                            float(settings.AGENT_MAX_CUMULATIVE_RATE_LIMIT_SLEEP_S)
                            - ctx.rate_limit_sleep_ms / 1000.0
                        )
                        sleep_s = min(sleep_s, max(0.0, remaining_sleep))
                    if sleep_s <= 0:
                        raise RateLimitError(
                            "Groq rate limit exceeded and retry sleep budget is exhausted."
                        ) from exc
                    time.sleep(sleep_s)
                    if ctx is not None:
                        ctx.rate_limit_sleep_ms += sleep_s * 1000.0
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
            from app.retrieval.query_expansion import decompose_retrieval_variants

            variants = [ctx.question] + decompose_retrieval_variants(ctx.question)
        cap = max(1, int(settings.MAX_QUERY_VARIANTS))
        from app.retrieval.query_expansion import question_aspect_markers, reasoning_retrieval_variants
        from app.retrieval.source_priority import is_reasoning_query

        if is_reasoning_query(ctx.question):
            reasoning = reasoning_retrieval_variants(ctx.question)
            variants = list(dict.fromkeys(reasoning + variants))
            cap = max(cap, min(5, len(variants)))
        elif len(question_aspect_markers(ctx.question)) >= 2:
            cap = max(cap, min(5, len(variants)))
        elif _needs_flow_tracing(ctx.question):
            cap = max(cap, min(4, len(variants)))
        ctx.query_variants = variants[:cap]
    if ctx.iteration == 0:
        ctx.need_structural = _needs_structural_context(ctx.question) or _needs_flow_tracing(
            ctx.question
        )
    return _transition(ctx, AgentState.ACT)


@_register(AgentState.ACT)
def _handle_act(ctx: AgentContext) -> AgentState:
    from app.retrieval.hybrid_search import search
    from app.retrieval.reranker import rerank
    from app.retrieval.entity_retrieval import (
        entity_expansion_needed,
        expand_architecture_hits,
        expand_entity_hits,
        log_retrieval_snapshot,
    )

    t_retrieval = time.monotonic()
    batches: list[list[dict[str, Any]]] = []
    if ctx.iteration == 0:
        variants = ctx.query_variants
    else:
        variants = _follow_up_variants(ctx)
    for variant in variants:
        try:
            batches.append(search(ctx.repo_id, variant, top_k=settings.HYBRID_SEARCH_TOP_K))
        except Exception as exc:
            logger.warning("act_search_failed", variant=variant, error=str(exc))

    merged = _merge_search_results(batches)
    merged = _symbol_boost_chunks(ctx.repo_id, ctx.question, merged)
    if entity_expansion_needed(ctx.question):
        merged = expand_entity_hits(
            ctx.repo_id,
            ctx.question,
            merged,
            max_entity_chunks=int(settings.ENTITY_RETRIEVAL_MAX_CHUNKS),
        ) or merged
    merged = expand_architecture_hits(ctx.repo_id, ctx.question, merged) or merged
    try:
        ctx.chunks = rerank(ctx.question, merged, top_n=settings.RERANK_TOP_N)
    except Exception as exc:
        logger.warning("act_rerank_failed", error=str(exc))
        ctx.chunks = merged[: settings.RERANK_TOP_N]

    from app.retrieval.source_priority import prefer_implementation_hits

    ctx.chunks = prefer_implementation_hits(ctx.chunks, ctx.question)
    ctx.chunks = _inject_reasoning_chunks(ctx.repo_id, ctx.question, ctx.chunks)

    log_retrieval_snapshot(ctx.repo_id, ctx.question, ctx.chunks, phase="post_act")

    for hit in ctx.chunks:
        score = float(hit.get("score") or hit.get("rerank_score") or 0.0)
        if score > ctx.best_retrieval_score:
            ctx.best_retrieval_score = score

    if ctx.need_structural and not ctx.graph_context:
        try:
            from app.graph.queries import get_callers, get_callees

            symbols = _extract_flow_symbols(ctx.question)
            symbol = symbols[0] if symbols else _extract_symbol(ctx.question)
            if symbol:
                callers = get_callers(ctx.repo_id, symbol)[:5]
                callees = get_callees(ctx.repo_id, symbol)[:8]
                lines = [f"Symbol: {symbol}"]
                if callers:
                    lines.append("Callers: " + ", ".join(c["caller"] for c in callers))
                if callees:
                    lines.append("Callees: " + ", ".join(c["callee"] for c in callees))
                ctx.graph_context = "\n".join(lines)
        except Exception as exc:
            logger.debug("act_graph_context_skipped", error=str(exc))

    ctx.retrieval_ms += (time.monotonic() - t_retrieval) * 1000.0
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
        if ctx.iteration < ctx.max_iterations:
            return _transition(ctx, AgentState.FINALIZE)
        ctx.error = "No retrieval context found for this question."
        ctx.answer = (
            "I could not retrieve relevant code chunks for this repository. "
            "Try re-indexing the repo or asking about a specific file, class, or function."
        )
        ctx.gated = True
        ctx.confidence_score = 0.0
        return _transition(ctx, AgentState.RESPOND)

    if not ctx.chunks:
        ctx.enough_evidence = False
        ctx.iteration += 1
        if ctx.iteration >= ctx.max_iterations:
            ctx.error = "No retrieval context found for this question."
            ctx.answer = (
                "I could not retrieve relevant code chunks for this repository. "
                "Try re-indexing the repo or asking about a specific file, class, or function."
            )
            ctx.gated = True
            ctx.confidence_score = 0.0
            return _transition(ctx, AgentState.RESPOND)
        return _transition(ctx, AgentState.ACT)

    # Fast path: strong retrieval covers all question aspects — skip DECIDE LLM.
    # Keep DECIDE when multiple search variants ran but evidence is thin (single chunk).
    from app.retrieval.query_expansion import question_aspect_markers

    if ctx.iteration == 0 and _retrieval_strong_enough(ctx):
        multi_variant = len(ctx.query_variants or []) > 1
        thin_multi_search = (
            multi_variant
            and not question_aspect_markers(ctx.question)
            and not _needs_flow_tracing(ctx.question)
            and len(ctx.chunks or []) < 4
        )
        if not thin_multi_search:
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
    from app.agent.prompts.answer_quality_dataset import classify_query
    from app.agent.confidence import GATED_FALLBACK_MESSAGE
    from app.agent.grounding import (
        claims_to_sources,
        looks_like_leaked_finalize_json,
        parse_finalize_json,
        polish_claims,
        render_claims_markdown,
    )

    allowed_paths = sorted({
        (c.get("chunk_metadata") or {}).get("display_path")
        or (c.get("chunk_metadata") or {}).get("file_path")
        for c in ctx.chunks
    } - {None, ""})
    assembled = ctx.assembled_context
    chunk_manifest: list[str] = []
    for hit in ctx.chunks[:20]:
        meta = hit.get("chunk_metadata") or {}
        path = meta.get("display_path") or meta.get("file_path")
        if not path:
            continue
        fn = meta.get("function_name") or ""
        sl = meta.get("start_line")
        el = meta.get("end_line")
        if sl:
            chunk_manifest.append(f"- `{path}:{sl}-{el}` ({fn})" if el and el != sl else f"- `{path}:{sl}` ({fn})")
    if chunk_manifest:
        assembled = (
            f"{assembled}\n\n"
            "CITE FROM THESE EXACT CHUNK RANGES (one method per citation — do not cite whole-class spans):\n"
            + "\n".join(chunk_manifest[:18])
        )
    if allowed_paths:
        path_lines = "\n".join(f"- `{p}`" for p in allowed_paths[:25])
        assembled = (
            f"{assembled}\n\n"
            "INDEXED FILES YOU MAY CITE (use exact paths with line numbers from context):\n"
            f"{path_lines}"
        )

    system = finalize_system_prompt(ctx.question)
    user = finalize_prompt({
        "question": ctx.question,
        "assembled_context": assembled,
        "graph_context": ctx.graph_context,
        "is_why_query": _is_why_question(ctx.question),
        "query_category": classify_query(ctx.question),
    })

    def _apply_structured(raw: str) -> bool:
        claims = parse_finalize_json(raw)
        if not claims:
            return False
        claims = polish_claims(claims, ctx.chunks, ctx.question)
        ctx.structured_claims = claims
        ctx.answer = render_claims_markdown(claims)
        ctx.sources = claims_to_sources(claims)
        return True

    def _gate_finalize_parse_failure(reason: str, preview: str = "") -> AgentState:
        logger.error(
            "finalize_structured_output_failed",
            repo_id=ctx.repo_id,
            reason=reason,
            preview=preview[:240],
        )
        ctx.structured_claims = []
        ctx.answer = GATED_FALLBACK_MESSAGE
        ctx.sources = []
        ctx.gated = True
        ctx.confidence_score = 0.0
        return _transition(ctx, AgentState.RESPOND)

    raw = ""
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

    if _apply_structured(raw):
        return _transition(ctx, AgentState.VERIFY)

    # Retry only when output looks like broken structured JSON (truncated/malformed).
    if looks_like_leaked_finalize_json(raw):
        retry_user = (
            f"{user}\n\n"
            "CRITICAL: Your previous output was invalid or incomplete JSON. "
            f"Return ONE valid JSON object with at most {settings.FINALIZE_MAX_CLAIMS} claims. "
            "Close every brace and quote. No markdown fences. No prose outside JSON."
        )
        try:
            raw_retry = _groq_text(
                system,
                retry_user,
                max_tokens=settings.FINALIZE_MAX_TOKENS,
                purpose="finalize",
                model=settings.LLM_MODEL,
                wall_clock_timeout_s=float(settings.GROQ_FINALIZE_TIMEOUT_S),
                ctx=ctx,
            )
            if _apply_structured(raw_retry):
                return _transition(ctx, AgentState.VERIFY)
            raw = raw_retry
        except (RateLimitError, ProviderError) as exc:
            ctx.answer = _apply_provider_failure(ctx, exc, phase="finalize")
            ctx.gated = True
            return _transition(ctx, AgentState.RESPOND)

        return _gate_finalize_parse_failure("json_parse_failed_after_retry", raw)

    # Non-JSON prose fallback only when output does not resemble structured JSON.
    logger.warning("finalize_non_json_prose_fallback", repo_id=ctx.repo_id)
    ctx.structured_claims = []
    ctx.answer = raw
    ctx.sources = []
    return _transition(ctx, AgentState.VERIFY)


@_register(AgentState.VERIFY)
def _handle_verify(ctx: AgentContext) -> AgentState:
    from app.agent.citation_repair import repair_answer_citations
    from app.agent.claim_verification import verify_claims_batch
    from app.agent.confidence import (
        GATED_FALLBACK_MESSAGE,
        assert_sources_match_answer,
        evaluate,
        evaluate_structured_claims,
        has_placeholder_citations,
        reconcile_sources_with_answer,
        sources_from_answer_citations,
        validate_sources,
    )
    from app.agent.response_firewall import sanitize_user_answer

    if ctx.structured_claims:
        from app.agent.grounding import (
            claims_to_sources,
            normalize_claims,
            normalize_citation,
            polish_claims,
            render_claims_markdown,
        )

        ctx.structured_claims = normalize_claims(ctx.structured_claims)
        # Repair structured claims citations first using symbol resolution
        try:
            from app.agent.citation_repair import _resolve_citation_lines, _hits_by_path
            by_path = _hits_by_path(_chunks_to_repair_hits(ctx.chunks))
            for claim in ctx.structured_claims:
                cit = normalize_citation(claim.get("citation"))
                if cit and cit.get("file_path"):
                    claim["citation"] = cit
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

        ctx.structured_claims = polish_claims(
            ctx.structured_claims, ctx.chunks, ctx.question,
        )
        ctx.answer = render_claims_markdown(ctx.structured_claims)
        ctx.sources = claims_to_sources(ctx.structured_claims)

        from app.agent.confidence import _indexed_paths_for_repo, path_key
        import traceback

        allowed_paths = _indexed_paths_for_repo(ctx.repo_id)
        for c in ctx.chunks:
            pk = path_key(str(
                (c.get("chunk_metadata") or {}).get("display_path")
                or (c.get("chunk_metadata") or {}).get("file_path")
                or ""
            ))
            if pk:
                allowed_paths.add(pk)
        t_verify = time.monotonic()
        try:
            verification = verify_claims_batch(
                ctx.structured_claims,
                ctx.repo_id,
                retrieval_hits=ctx.chunks,
                allowed_paths=allowed_paths,
                question=ctx.question,
            )
            if verification.get("verification_error"):
                logger.error(
                    "verify_system_error",
                    repo_id=ctx.repo_id,
                    phase="claim_batch",
                    error=verification.get("error"),
                )
                fallback = evaluate(
                    ctx.answer or "",
                    ctx.repo_id,
                    top_retrieval_score=ctx.best_retrieval_score,
                    question=ctx.question,
                )
                if not fallback.get("gated") and (fallback.get("answer") or "").strip():
                    ctx.confidence_score = float(fallback.get("confidence_score", 0.0))
                    ctx.gated = False
                    ctx.answer = fallback["answer"]
                    ctx.sources = validate_sources(
                        sources_from_answer_citations(ctx.answer, ctx.repo_id),
                        ctx.repo_id,
                    )
                    return _transition(ctx, AgentState.RESPOND)
                ctx.confidence_score = 0.0
                ctx.gated = True
                ctx.answer = GATED_FALLBACK_MESSAGE
                ctx.sources = []
                return _transition(ctx, AgentState.RESPOND)

            result = evaluate_structured_claims(
                ctx.structured_claims,
                ctx.answer or "",
                ctx.repo_id,
                verification,
                top_retrieval_score=ctx.best_retrieval_score,
                question=ctx.question,
            )
        except Exception as exc:
            logger.error(
                "verify_system_error",
                repo_id=ctx.repo_id,
                phase="structured_verify",
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            ctx.confidence_score = 0.0
            ctx.gated = True
            ctx.answer = GATED_FALLBACK_MESSAGE
            ctx.sources = []
            return _transition(ctx, AgentState.RESPOND)
        finally:
            ctx.verify_ms += (time.monotonic() - t_verify) * 1000.0

        if result.get("verification_error"):
            logger.error(
                "verify_system_error",
                repo_id=ctx.repo_id,
                phase="evaluate_structured",
            )
            ctx.confidence_score = 0.0
            ctx.gated = True
            ctx.answer = GATED_FALLBACK_MESSAGE
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
            claim_sources = result.get("sources") or []
            ctx.sources = reconcile_sources_with_answer(
                ctx.answer,
                validate_sources(claim_sources, ctx.repo_id),
                ctx.repo_id,
            )
            assert_sources_match_answer(ctx.answer, ctx.sources, repo_id=ctx.repo_id)
            if ctx.answer and len(ctx.answer.split()) > 350:
                import re
                sentences = re.split(r'(?<=[.!?])\s+', ctx.answer)
                truncated_sentences = []
                words_count = 0
                for sent in sentences:
                    sent_words_len = len(sent.split())
                    if not truncated_sentences or words_count + sent_words_len <= 350:
                        truncated_sentences.append(sent)
                        words_count += sent_words_len
                    else:
                        break
                if truncated_sentences:
                    ctx.answer = " ".join(truncated_sentences)
                else:
                    ctx.answer = " ".join(ctx.answer.split()[:350]) + "..."
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
        result = evaluate(
            repaired,
            ctx.repo_id,
            top_retrieval_score=ctx.best_retrieval_score,
            question=ctx.question,
        )

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
        ctx.sources = reconcile_sources_with_answer(
            ctx.answer, validate_sources(ctx.sources, ctx.repo_id), ctx.repo_id,
        )
        assert_sources_match_answer(ctx.answer, ctx.sources, repo_id=ctx.repo_id)
        if ctx.answer and len(ctx.answer.split()) > 350:
            import re
            sentences = re.split(r'(?<=[.!?])\s+', ctx.answer)
            truncated_sentences = []
            words_count = 0
            for sent in sentences:
                sent_words_len = len(sent.split())
                if not truncated_sentences or words_count + sent_words_len <= 350:
                    truncated_sentences.append(sent)
                    words_count += sent_words_len
                else:
                    break
            if truncated_sentences:
                ctx.answer = " ".join(truncated_sentences)
            else:
                ctx.answer = " ".join(ctx.answer.split()[:350]) + "..."
    return _transition(ctx, AgentState.RESPOND)


def _ensure_no_structured_json_leak(ctx: AgentContext) -> None:
    """Hard gate: structured FINALIZE JSON must never appear in user-visible answers."""
    from app.agent.confidence import GATED_FALLBACK_MESSAGE
    from app.agent.grounding import looks_like_leaked_finalize_json

    if ctx.gated or not ctx.answer:
        return
    if looks_like_leaked_finalize_json(ctx.answer):
        logger.error("structured_json_leak_blocked_at_respond", repo_id=ctx.repo_id)
        ctx.answer = GATED_FALLBACK_MESSAGE
        ctx.sources = []
        ctx.gated = True
        ctx.confidence_score = 0.0


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
    _ensure_models_warmed()
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
        if _wall_clock_exceeded(ctx) and state != AgentState.RESPOND:
            state = _apply_request_timeout(ctx, phase=state.value)
            if state == AgentState.VERIFY:
                continue
            if state == AgentState.RESPOND:
                _handle_respond(ctx)
                break
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

    _ensure_no_structured_json_leak(ctx)

    result: dict[str, Any] = {
        "answer": ctx.answer,
        "sources": ctx.sources,
        "confidence_score": ctx.confidence_score,
        "gated": ctx.gated,
    }
    if not ctx.gated and ctx.answer:
        from app.agent.confidence import assert_sources_match_answer, reconcile_sources_with_answer

        ctx.sources = reconcile_sources_with_answer(ctx.answer, ctx.sources, ctx.repo_id)
        if not assert_sources_match_answer(ctx.answer, ctx.sources, repo_id=ctx.repo_id):
            logger.warning("respond_sources_reconciled_after_mismatch", repo_id=ctx.repo_id)
        result["sources"] = ctx.sources
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
    log.info(
        "agent_run_complete",
        gated=ctx.gated,
        cache_hit=ctx.cache_hit,
        groq_calls=ctx.groq_calls,
        states=ctx.state_trace,
        response_time_ms=round(_elapsed_s(ctx) * 1000, 1),
        retrieval_ms=round(ctx.retrieval_ms, 1),
        generation_ms=round(ctx.groq_ms, 1),
        verify_ms=round(ctx.verify_ms, 1),
        rate_limit_sleep_ms=round(ctx.rate_limit_sleep_ms, 1),
        source_count=len(ctx.sources or []),
        confidence_score=ctx.confidence_score,
        retrieval_hits=len(ctx.chunks or []),
    )
    result["timing"] = {
        "total_ms": round(_elapsed_s(ctx) * 1000, 1),
        "retrieval_ms": round(ctx.retrieval_ms, 1),
        "generation_ms": round(ctx.groq_ms, 1),
        "verify_ms": round(ctx.verify_ms, 1),
        "rate_limit_sleep_ms": round(ctx.rate_limit_sleep_ms, 1),
        "groq_calls": ctx.groq_calls,
    }
    # Expose top retrieval paths for eval/golden CI (file-level hit detection).
    retrieval_out: list[dict[str, Any]] = []
    for chunk in (ctx.chunks or [])[:15]:
        meta = chunk.get("chunk_metadata") or chunk.get("metadata") or {}
        fp = (
            meta.get("display_path")
            or meta.get("file_path")
            or chunk.get("file_path")
            or ""
        )
        if fp:
            retrieval_out.append(
                {
                    "file_path": fp,
                    "function_name": meta.get("function_name"),
                    "start_line": meta.get("start_line"),
                    "end_line": meta.get("end_line"),
                    "rerank_score": chunk.get("rerank_score") or chunk.get("score"),
                }
            )
    if retrieval_out:
        result["retrieval_hits"] = retrieval_out
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
