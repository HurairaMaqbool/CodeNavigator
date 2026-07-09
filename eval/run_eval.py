# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/run_eval.py
----------------
Executes RAGAS evaluation against a real, already-ingested fixture repo.
Guarantees zero-cost by strictly importing judge wrappers.
"""
from __future__ import annotations

import os
os.environ["GIT_PYTHON_REFRESH"] = "quiet"

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# NOTE: datasets / ragas are imported lazily inside run_eval() so this module
# (and the helpers below) stay importable even when the eval stack isn't
# installed or is version-mismatched. ragas 0.3.2 imports a vertexai path that
# langchain-community 0.4.x removed; pin via requirements-eval.txt to run evals.
from app.agent.loop import answer_question
from eval.context_builder import build_ragas_contexts
from eval.eval_store import append_run, load_runs, update_last_run
from eval.groq_guard import GroqQuotaError, eval_question_delay, require_groq_quota
from eval.health_check import (
    EvalPipelineError,
    check_index_health,
    check_agent_probe,
    diagnose_pipeline_failure,
    resolve_asset_repo_id,
)
from eval.retrieval_metrics import precision_at_k


class RegressionError(Exception):
    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _find_comparable_baseline(
    prior_runs: list[dict],
    question_count: int,
) -> dict | None:
    """Compare only against the most recent run with the same question count."""
    for run in reversed(prior_runs):
        prev_n = (run.get("diagnostics") or {}).get("question_count")
        if prev_n == question_count and run.get("ragas_scores"):
            return run
    return None


def _check_regressions(
    prev_scores: dict[str, float],
    curr_scores: dict[str, float],
) -> list[str]:
    regressions: list[str] = []
    for metric, prev_val in prev_scores.items():
        curr_val = curr_scores.get(metric, 0.0)
        if metric == "answer_relevancy" and curr_scores.get("faithfulness", 0) >= 0.65:
            threshold = 0.75
        else:
            threshold = 0.90
        if prev_val > 0 and curr_val < prev_val * threshold:
            regressions.append(f"{metric} dropped from {prev_val:.3f} to {curr_val:.3f}")
    return regressions


def _extract_ragas_scores(ragas_result, metrics_list: list[str]) -> dict[str, float]:
    """
    Version-robust extraction of mean per-metric scores.

    RAGAS >= 0.1 returns an EvaluationResult object (not a dict), so the old
    `result.items()` access raises 'EvaluationResult has no attribute items'.
    The canonical, stable API across 0.2/0.3 is `.to_pandas()`; we fall back to
    subscript access only if that is unavailable.
    """
    scores: dict[str, float] = {}
    df = None
    try:
        df = ragas_result.to_pandas()
    except Exception:
        df = None

    for m in metrics_list:
        try:
            if df is not None and m in df.columns:
                col = df[m].dropna()
                scores[m] = float(col.mean()) if len(col) else 0.0
            else:
                raw = ragas_result[m]
                valid = [float(v) for v in raw if v == v]
                scores[m] = sum(valid) / len(valid) if valid else 0.0
        except Exception:
            scores[m] = 0.0
    return scores


def run_eval(dataset_path: str = "tests/eval_set.json") -> dict:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    try:
        from ragas.run_config import RunConfig
    except Exception:  # pragma: no cover - older ragas
        RunConfig = None
    from eval.ragas_providers import get_judge_llm, get_judge_embeddings

    eval_set_path = Path(dataset_path)
    if not eval_set_path.exists():
        raise FileNotFoundError(f"{eval_set_path} not found")

    with eval_set_path.open("r", encoding="utf-8") as f:
        eval_data = json.load(f)
        if isinstance(eval_data, dict) and "entries" in eval_data:
            eval_data = eval_data["entries"]

    if not eval_data:
        raise ValueError("Eval set is empty")

    # Free-tier Groq trips on bursts; allow shrinking the set for a smoke run.
    try:
        max_q = int(os.environ.get("EVAL_MAX_QUESTIONS", "0"))
    except ValueError:
        max_q = 0
    if max_q > 0:
        eval_data = eval_data[:max_q]

    job_id = eval_data[0].get("repo_id", "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d")
    meta, asset_repo_id = resolve_asset_repo_id(job_id)
    if not meta or meta.sync_status != "synced":
        raise ValueError(
            f"Precondition failed: Repo {job_id} is not fully ingested "
            f"(status: {getattr(meta, 'sync_status', 'missing')})"
        )

    health = check_index_health(asset_repo_id)
    health.raise_if_failed()
    if not os.environ.get("EVAL_SKIP_AGENT_PROBE", "1").strip().lower() in ("0", "false", "no"):
        agent_health = check_agent_probe(asset_repo_id)
        agent_health.raise_if_failed()
    if asset_repo_id != job_id:
        print(f"Resolved job_id {job_id[:12]}... -> asset_repo_id {asset_repo_id[:12]}...")

    try:
        require_groq_quota()
    except GroqQuotaError as exc:
        raise EvalPipelineError(str(exc), diagnostics=exc.details) from exc

    questions = []
    answers = []
    contexts = []
    ground_truths = []
    
    total_iterations = 0
    total_confidence = 0.0
    total_invalid_ratio = 0.0
    total_precision_at_3 = 0.0

    gated_count = 0
    empty_source_count = 0
    sentinel_context_count = 0
    rate_limited_count = 0
    per_question: list[dict] = []

    print(f"Running eval against {len(eval_data)} questions on asset {asset_repo_id}...")

    for i, case in enumerate(eval_data):
        if i > 0:
            eval_question_delay()
        question = case["question"]
        # Hit the LIVE pipeline directly (no semantic cache bypasses here!)
        res = answer_question(question, repo_id=asset_repo_id)

        ans_text = res.get("answer", "")
        if res.get("rate_limited"):
            rate_limited_count += 1
        elif "rate-limited" in ans_text.lower():
            rate_limited_count += 1
        ctx_list, used_sentinel = build_ragas_contexts(res)
        if used_sentinel:
            sentinel_context_count += 1

        if res.get("gated"):
            gated_count += 1
        if not res.get("sources"):
            empty_source_count += 1

        questions.append(question)
        answers.append(ans_text)
        contexts.append(ctx_list)
        # RAGAS >= 0.2.x expects a string for reference/ground_truth, not a list.
        ground_truths.append(case["ground_truth_answer_summary"])

        total_iterations += len(res.get("trace", []))
        total_confidence += res.get("confidence_score", 0.0)
        total_invalid_ratio += (res.get("invalid_reference_ratio") or 0.0)

        gt_files = case.get("ground_truth_files", [])
        p_at_3, top_files, gt_hit = precision_at_k(res, gt_files, k=3)
        total_precision_at_3 += p_at_3

        per_question.append({
            "question": question,
            "precision_at_3": round(p_at_3, 4),
            "top_files": top_files,
            "ground_truth_files": gt_files,
            "gt_hit": gt_hit,
            "gated": bool(res.get("gated")),
            "confidence_score": round(float(res.get("confidence_score") or 0.0), 4),
            "context_count": len(ctx_list),
            "used_sentinel": used_sentinel,
            "rate_limited": bool(res.get("rate_limited")),
        })

    N = len(eval_data)

    if rate_limited_count > 0:
        raise EvalPipelineError(
            f"Evaluation aborted: Groq API quota exhausted during agent phase "
            f"({rate_limited_count}/{N} questions rate-limited).\n"
            "Fix: wait for daily reset, switch LLM_MODEL to llama-3.1-8b-instant in .env, "
            "or upgrade Groq tier. Scores were not stored.",
            diagnostics={
                "rate_limited_count": rate_limited_count,
                "question_count": N,
                "asset_repo_id": asset_repo_id,
            },
        )
    
    # Build Dataset
    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths
    })

    # Execute Ragas explicitly passing judges
    judge_llm = get_judge_llm()
    judge_embeddings = get_judge_embeddings()

    # CRITICAL: serialize judge calls. RAGAS defaults to ~16 concurrent workers,
    # which instantly trips the free Groq tier tokens-per-minute limit and makes
    # every metric return NaN -> 0.000. max_workers=1 + retries trades speed for
    # a deterministic, rate-limit-safe run.
    eval_kwargs: dict = {
        "llm": judge_llm,
        "embeddings": judge_embeddings,
    }
    if RunConfig is not None:
        eval_kwargs["run_config"] = RunConfig(
            timeout=300,
            max_retries=8,
            max_wait=90,
            max_workers=1,
        )

    ragas_result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        **eval_kwargs,
    )

    metrics_list = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    ragas_scores = _extract_ragas_scores(ragas_result, metrics_list)

    # Get git SHA and version
    _project_root = Path(__file__).resolve().parent.parent
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_project_root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        git_sha = "unknown"

    try:
        git_short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_project_root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        git_short = "unknown"

    if git_short == "unknown":
        from app.observability.logging_config import logger
        fallback_version = f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        logger.warning("git_not_available_using_fallback", fallback_version=fallback_version)
        version = os.environ.get("EVAL_VERSION", fallback_version)
    else:
        version = os.environ.get("EVAL_VERSION", git_short)

    diagnostics = {
        "job_id": job_id,
        "asset_repo_id": asset_repo_id,
        "question_count": N,
        "gated_count": gated_count,
        "empty_source_count": empty_source_count,
        "sentinel_context_count": sentinel_context_count,
        "mean_confidence_score": total_confidence / N,
        "retrieval_precision_at_3": total_precision_at_3 / N,
        "per_question": per_question,
    }

    is_failure, failure_reason = diagnose_pipeline_failure(
        ragas_scores,
        question_count=N,
        gated_count=gated_count,
        empty_source_count=empty_source_count,
        sentinel_context_count=sentinel_context_count,
        retrieval_precision_at_3=total_precision_at_3 / N,
        mean_confidence=total_confidence / N,
    )
    if is_failure:
        raise EvalPipelineError(
            "Evaluation aborted: pipeline failure detected (scores not stored).\n"
            f"Reason: {failure_reason}\n"
            f"Diagnostics: gated={gated_count}/{N}, empty_sources={empty_source_count}/{N}, "
            f"sentinel_contexts={sentinel_context_count}/{N}, P@3={total_precision_at_3 / N:.3f}",
            diagnostics={**diagnostics, "ragas_scores": ragas_scores, "failure_reason": failure_reason},
        )

    record = {
        "version": version,
        "git_sha": git_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ragas_scores": ragas_scores,
        "mean_confidence_score": total_confidence / N,
        "average_iterations": total_iterations / N,
        "invalid_reference_rate": total_invalid_ratio / N,
        "retrieval_precision_at_3": total_precision_at_3 / N,
        "diagnostics": diagnostics,
    }

    previous_runs = load_runs()
    append_run(record)

    # Regression check — only vs same question-count baseline (3-Q vs 10-Q is not comparable)
    baseline = _find_comparable_baseline(previous_runs, N)
    if baseline:
        prev_scores = baseline.get("ragas_scores", {})
        curr_scores = record.get("ragas_scores", {})
        regressions = _check_regressions(prev_scores, curr_scores)
        if regressions:
            diag_lines = [
                f"gated {gated_count}/{N}",
                f"empty sources {empty_source_count}/{N}",
                f"P@3 {total_precision_at_3 / N:.3f}",
                f"asset_repo_id {asset_repo_id[:16]}...",
                f"compared_to {baseline.get('version', 'prior')} (n={N})",
            ]
            msg = "Regression detected in evaluation:\n" + "\n".join(regressions)
            msg += "\n\nDiagnostics: " + ", ".join(diag_lines)
            record["regression_warning"] = msg
            record["regression_baseline_version"] = baseline.get("version")
            update_last_run({
                "regression_warning": msg,
                "regression_baseline_version": baseline.get("version"),
            })

    return record

if __name__ == "__main__":
    import sys
    try:
        result = run_eval()
        print(result)
        if result.get("regression_warning"):
            print(f"\n[WARN] {result['regression_warning']}")
            sys.exit(0)
    except RegressionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except EvalPipelineError as e:
        print(f"\n[PIPELINE FAIL] {e}")
        sys.exit(2)
    except GroqQuotaError as e:
        print(f"\n[QUOTA BLOCKED] {e}")
        sys.exit(3)
