# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""eval/health_check.py — pre-evaluation gates (delegates readiness to repo_readiness)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ingestion.repo_readiness import is_repo_ready, readiness_snapshot
from app.retrieval.bm25_store import _index_path_for
from app.retrieval.vector_store import get_collection


@dataclass
class HealthCheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise EvalPreconditionError(
                "Pre-evaluation health check failed:\n" + "\n".join(f"  - {e}" for e in self.errors),
                details=self.details,
            )


class EvalPreconditionError(Exception):
    """Raised when the system is not safe to evaluate."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class EvalPipelineError(Exception):
    """Raised when evaluation completed but results indicate pipeline failure."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def resolve_asset_repo_id(job_id: str) -> tuple[Any, str]:
    """Backward-compatible wrapper — see app.repo_resolver."""
    from app.repo_resolver import resolve_asset_repo_id as _resolve

    return _resolve(job_id)


def check_index_health(
    asset_repo_id: str,
    *,
    min_chunks: int = 50,
    probe_query: str = "PreparedRequest class requests",
) -> HealthCheckResult:
    errors: list[str] = []
    details: dict[str, Any] = {"asset_repo_id": asset_repo_id}

    collection = get_collection(asset_repo_id)
    chunk_count = collection.count() if collection else 0
    details["chroma_chunk_count"] = chunk_count
    if chunk_count < min_chunks:
        errors.append(
            f"Chroma collection for {asset_repo_id[:12]}... has {chunk_count} chunks "
            f"(minimum {min_chunks}). Re-ingest may be incomplete or querying wrong repo_id."
        )

    bm25_path = _index_path_for(asset_repo_id)
    details["bm25_index_path"] = str(bm25_path)
    if not bm25_path.exists():
        errors.append(f"BM25 index missing at {bm25_path}")

    if not errors:
        try:
            from app.agent.llm_client import get_llm_client
            from app.retrieval.hybrid_search import search_code

            llm = get_llm_client()
            hits = search_code(probe_query, asset_repo_id, llm, top_k=3)
            details["probe_hit_count"] = len(hits)
            if not hits:
                errors.append(
                    f"Hybrid search returned 0 hits for probe query on {asset_repo_id[:12]}..."
                )
        except Exception as exc:
            errors.append(f"Hybrid search probe failed: {exc}")

    return HealthCheckResult(ok=not errors, errors=errors, details=details)


def check_agent_probe(
    asset_repo_id: str,
    *,
    probe_question: str = "What is the PreparedRequest class in requests?",
) -> HealthCheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"asset_repo_id": asset_repo_id}

    try:
        from app.agent.loop import answer_question

        res = answer_question(probe_question, repo_id=asset_repo_id)
        retrieval_count = len(res.get("retrieval_hits") or [])
        details["gated"] = bool(res.get("gated"))
        details["source_count"] = len(res.get("sources") or [])
        details["retrieval_hit_count"] = retrieval_count
        details["confidence_score"] = res.get("confidence_score", 0.0)
        details["rate_limited"] = bool(res.get("rate_limited"))
        details["timed_out"] = bool(res.get("timed_out"))

        if res.get("rate_limited"):
            errors.append("Agent probe hit Groq rate limit — wait and retry before evaluating")
        elif res.get("timed_out"):
            errors.append("Agent probe timed out — backend may be cold; retry once models are warm")
        elif retrieval_count == 0:
            errors.append(
                "Agent probe retrieved zero context — retrieval pipeline is broken "
                "(index/embedding mismatch or wrong repo_id)"
            )
        elif res.get("gated"):
            warnings.append(
                f"Agent probe answer was confidence-gated (score={res.get('confidence_score', 0):.1f}) "
                f"but retrieval returned {retrieval_count} hits — evaluation may show lower scores."
            )
    except Exception as exc:
        errors.append(f"Agent probe failed: {exc}")

    details["warnings"] = warnings
    return HealthCheckResult(ok=not errors, errors=errors, details=details)


def run_full_eval_precheck(
    job_id: str,
    *,
    include_agent_probe: bool = True,
) -> HealthCheckResult:
    """Combined pre-evaluation gate — uses is_repo_ready (same path as /status)."""
    snap = readiness_snapshot(job_id)
    readiness = is_repo_ready(job_id)
    if not readiness.ready:
        status = snap["sync_status"] or "missing"
        return HealthCheckResult(
            ok=False,
            errors=[
                readiness.block_message
                or f"Repo not fully ingested (status: {status})"
            ],
            details={
                "job_id": job_id,
                "asset_repo_id": snap["asset_repo_id"],
                "sync_status": status,
                "files_parsed": snap["files_parsed"],
                "chunks_created": snap["chunks_created"],
                "block_reason": snap["block_reason"],
                "ready": False,
            },
        )

    asset_repo_id = snap["asset_repo_id"]
    index_health = check_index_health(asset_repo_id)
    if not index_health.ok:
        return index_health

    details = {
        **index_health.details,
        **snap,
        "ready": True,
    }
    if asset_repo_id != job_id:
        details["alias_resolved"] = True

    if include_agent_probe:
        agent_health = check_agent_probe(asset_repo_id)
        details.update(agent_health.details)
        if not agent_health.ok:
            return HealthCheckResult(ok=False, errors=agent_health.errors, details=details)

    return HealthCheckResult(ok=True, details=details)


def diagnose_pipeline_failure(
    ragas_scores: dict[str, float],
    *,
    question_count: int,
    gated_count: int,
    empty_source_count: int,
    sentinel_context_count: int,
    retrieval_precision_at_3: float,
    mean_confidence: float,
) -> tuple[bool, str]:
    faithfulness = ragas_scores.get("faithfulness", 0.0)
    metrics = [ragas_scores.get(k, 0.0) for k in ("answer_relevancy", "context_precision", "context_recall")]
    all_three_zero = all(v == 0.0 for v in metrics)

    if faithfulness == 0.0 and any(ragas_scores.get(k, 0) > 0.5 for k in ("answer_relevancy", "context_precision", "context_recall")):
        return True, "faithfulness is 0.000 while other RAGAS metrics are non-zero — judge partial failure (do not trust scores)"

    if not all_three_zero:
        return False, ""

    reasons: list[str] = []
    if sentinel_context_count == question_count:
        reasons.append(
            f"all {question_count} questions had empty retrieval context "
            "(only sentinel '(no context retrieved)' was passed to RAGAS)"
        )
    if empty_source_count == question_count:
        reasons.append(f"agent returned zero sources on all {question_count} questions")
    if gated_count >= max(1, int(question_count * 0.7)):
        reasons.append(
            f"{gated_count}/{question_count} answers were confidence-gated "
            f"(mean confidence {mean_confidence:.1f}, threshold typically 4.0)"
        )
    if retrieval_precision_at_3 == 0.0:
        reasons.append("retrieval P@3 is 0.000 — no ground-truth file matched in top-3 sources")

    if not reasons:
        reasons.append(
            "all three RAGAS metrics are exactly 0.000 — likely judge LLM failure "
            "(rate limit / API error) or systematically empty evaluation dataset"
        )

    return True, "; ".join(reasons)
