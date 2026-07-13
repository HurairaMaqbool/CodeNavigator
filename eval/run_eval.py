# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/run_eval.py
----------------
Module #28 — Automated quality regression testing (RAGAS + state-path consistency).

Exercises the live ``POST /chat`` stack end-to-end. Intended for scheduled /
pre-release runs — not every commit — to conserve Groq free-tier quota.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.config import settings
from app.ingestion.repo_readiness import is_repo_ready

from eval.context_builder import build_ragas_contexts
from eval.eval_store import append_run, load_runs, update_last_run
from eval.groq_guard import GroqQuotaError, eval_question_delay, ragas_judge_cooldown, require_groq_quota
from eval.health_check import (
    EvalPipelineError,
    check_index_health,
    check_agent_probe,
    diagnose_pipeline_failure,
    resolve_asset_repo_id,
)
from eval.retrieval_metrics import precision_at_k

# Version-controlled Golden Set (question + expected citations per entry).
DEFAULT_GOLDEN_SET_PATH = Path("data/golden_set.json")
FALLBACK_GOLDEN_SET_PATH = Path("tests/eval_set.json")

STATE_PATH_RUNS_DEFAULT = 1  # overridden at runtime from settings.EVAL_STATE_PATH_RUNS


class RegressionError(Exception):
    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _resolve_golden_path(
    golden_path: str | Path | None = None,
    *,
    target_repo_id: str | None = None,
) -> Path:
    if golden_path:
        return Path(golden_path)
    # Repo-scoped RAGAS must use per-repo questions (tests/eval_set.json has repo_id).
    if target_repo_id and FALLBACK_GOLDEN_SET_PATH.exists():
        return FALLBACK_GOLDEN_SET_PATH
    path = DEFAULT_GOLDEN_SET_PATH
    if not path.exists() and FALLBACK_GOLDEN_SET_PATH.exists():
        return FALLBACK_GOLDEN_SET_PATH
    return path


def _repo_id_aliases(job_or_asset_id: str) -> set[str]:
    """job_id + asset clone id for golden-set entry filtering."""
    _, asset = resolve_asset_repo_id(job_or_asset_id)
    ids = {job_or_asset_id}
    if asset:
        ids.add(asset)
    return ids


def _filter_golden_for_repo(
    entries: list[dict[str, Any]],
    target_repo_id: str,
) -> list[dict[str, Any]]:
    aliases = _repo_id_aliases(target_repo_id)
    with_repo = [e for e in entries if e.get("repo_id")]
    if not with_repo:
        return entries
    matched = [e for e in with_repo if e.get("repo_id") in aliases]
    return matched if matched else with_repo


def load_golden_set(
    golden_path: str | Path | None = None,
    *,
    target_repo_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Load Golden Set JSON — list of entries::

        {
          "repo_id": "...",
          "question": "...",
          "ground_truth_files": ["path/to/file.py"],   # expected citations
          "ground_truth_answer_summary": "...",
          "expected_gated": false                      # optional
        }
    """
    path = _resolve_golden_path(golden_path, target_repo_id=target_repo_id)
    if not path.exists():
        raise FileNotFoundError(f"Golden set not found at {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "entries" in raw:
        entries = list(raw["entries"])
    elif isinstance(raw, list):
        entries = raw
    else:
        raise ValueError(f"Invalid golden set format in {path}")

    if target_repo_id:
        entries = _filter_golden_for_repo(entries, target_repo_id)
    return entries


def _extract_state_path(chat_response: dict[str, Any]) -> list[str]:
    """
    Ordered state-transition log — list of AgentState enum names from loop.run().

    loop.py exposes this as ``trace: [{"state": "INTAKE"}, {"state": "PLAN"}, ...]``
    on the /chat JSON payload (no extra loop instrumentation required).
    """
    trace = chat_response.get("trace") or []
    return [str(item.get("state", "")) for item in trace if isinstance(item, dict)]


def _invoke_chat_endpoint(repo_id: str, question: str) -> dict[str, Any]:
    """Call the real ``POST /chat`` handler via FastAPI TestClient (full router → loop stack)."""
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from app.api.auth import verify_api_key
    from app.main import app
    from app.agent.loop import _EXACT_QUESTION_CACHE

    max_attempts = max(1, int(settings.GROQ_LLM_RATE_LIMIT_ATTEMPTS))
    last_error = ""

    for attempt in range(max_attempts):
        _EXACT_QUESTION_CACHE.clear()
        tenant = MagicMock(org_id="default")
        overrides = dict(app.dependency_overrides)
        app.dependency_overrides[verify_api_key] = lambda: None
        try:
            with (
                patch("app.platform.usage_meter.check_quota", return_value=True),
                patch("app.platform.usage_meter.increment"),
                patch("app.platform.audit_log.record_event"),
                patch("app.platform.tenant_context.get_tenant", return_value=tenant),
            ):
                client = TestClient(app)
                with patch.object(settings, "SEMANTIC_CACHE_ENABLED", False):
                    resp = client.post(
                        "/chat",
                        json={"repo_id": repo_id, "question": question},
                    )

            if resp.status_code == 200:
                return resp.json()

            body = resp.text[:500]
            last_error = f"/chat returned HTTP {resp.status_code}: {body}"
            if resp.status_code == 429 and attempt + 1 < max_attempts:
                wait_s = 30.0
                m = re.search(r"wait about (\d+) seconds", body, re.IGNORECASE)
                if m:
                    wait_s = float(m.group(1))
                wait_s = min(wait_s, float(settings.LLM_RATE_LIMIT_MAX_BACKOFF_S))
                time.sleep(wait_s)
                continue
            raise EvalPipelineError(
                last_error,
                diagnostics={"repo_id": repo_id, "question": question[:120]},
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides)

    raise EvalPipelineError(
        last_error or "chat endpoint failed after retries",
        diagnostics={"repo_id": repo_id, "question": question[:120]},
    )


def state_path_consistency(question: str, repo_id: str, n_runs: int = STATE_PATH_RUNS_DEFAULT) -> bool:
    """
    Run the same question ``n_runs`` times; require identical state-transition sequences.

    Compares ordered lists of state names from ``loop.run()``'s ``trace`` field.
    """
    if n_runs < 2:
        n_runs = 2
    paths: list[list[str]] = []
    for i in range(n_runs):
        if i > 0:
            eval_question_delay()
        res = _invoke_chat_endpoint(repo_id, question)
        paths.append(_extract_state_path(res))
    first = paths[0]
    return all(p == first for p in paths[1:])


def _find_comparable_baseline(prior_runs: list[dict], question_count: int) -> dict | None:
    for run in reversed(prior_runs):
        prev_n = (run.get("diagnostics") or {}).get("question_count")
        if prev_n == question_count and run.get("ragas_scores"):
            return run
    return None


def _check_ragas_regressions(prev_scores: dict[str, float], curr_scores: dict[str, float]) -> list[str]:
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


# Backward-compatible alias (test_fix_regressions.py)
_check_regressions = _check_ragas_regressions


def _extract_ragas_scores(ragas_result, metrics_list: list[str]) -> dict[str, float]:
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


def _per_row_ragas_scores(ragas_result, metrics_list: list[str]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    try:
        df = ragas_result.to_pandas()
        for _, row in df.iterrows():
            rows.append({m: float(row[m]) if m in row and row[m] == row[m] else 0.0 for m in metrics_list})
    except Exception:
        rows = []
    return rows


def _flag_gated_regressions(
    per_question: list[dict[str, Any]],
    golden_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag golden questions that flipped to gated=true when not expected."""
    flags: list[dict[str, Any]] = []
    for pq, case in zip(per_question, golden_entries):
        expected_gated = bool(case.get("expected_gated", False))
        actual_gated = bool(pq.get("gated", False))
        pq["expected_gated"] = expected_gated
        pq["gated_regression"] = (not expected_gated) and actual_gated
        if pq["gated_regression"]:
            flags.append({
                "question": pq.get("question", case.get("question", "")),
                "type": "gated_flip",
                "message": "Golden question returned gated=true unexpectedly — manual review required",
                "expected_gated": expected_gated,
                "actual_gated": actual_gated,
            })
    return flags


def _load_ragas_deps() -> tuple[Any, ...]:
    """Import RAGAS stack lazily; patch in tests via this hook."""
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
    except Exception:
        RunConfig = None
    from eval.ragas_providers import get_judge_llm, get_judge_embeddings

    return (
        Dataset,
        evaluate,
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
        RunConfig,
        get_judge_llm,
        get_judge_embeddings,
    )


def _run_ragas_evaluate(dataset: Any, metrics: list[Any], **kwargs: Any) -> Any:
    """Thin wrapper so tests can patch RAGAS without importing ragas at collection time."""
    from ragas import evaluate

    return evaluate(dataset=dataset, metrics=metrics, **kwargs)


def run_golden_set(
    golden_path: str | Path | None = None,
    *,
    target_repo_id: str | None = None,
) -> dict[str, Any]:
    """
    Module #28 entry point — score Golden Set via live /chat + RAGAS + state-path checks.

    Returns structured report (per-question + aggregate) consumable by compare_runs.py.
    """
    # Pre-check readiness BEFORE importing heavy RAGAS dependencies
    job_id = (target_repo_id or "").strip()
    if not job_id:
        raise ValueError(
            "Precondition failed: target_repo_id is required — pass the active session "
            "repo_id from the UI (same value /status and /eval/health use)."
        )

    readiness = is_repo_ready(job_id)
    if not readiness.ready:
        from app.ingestion.repo_readiness import readiness_snapshot

        snap = readiness_snapshot(job_id)
        status = snap["sync_status"] or "missing"
        raise ValueError(
            f"Precondition failed: Repo {job_id} is not fully ingested "
            f"(status: {status})"
        )

    # Now safe to import heavy dependencies after readiness check passes
    try:
        (
            Dataset,
            _evaluate,
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            RunConfig,
            get_judge_llm,
            get_judge_embeddings,
        ) = _load_ragas_deps()
    except ImportError as e:
        raise ImportError(
            f"RAGAS evaluation requires optional dependencies: {e}. "
            "Install with: pip install -r requirements.txt"
        ) from e

    path = _resolve_golden_path(golden_path, target_repo_id=target_repo_id)
    eval_data = load_golden_set(path, target_repo_id=target_repo_id)

    max_q = int(settings.EVAL_MAX_QUESTIONS)
    if max_q > 0:
        eval_data = eval_data[:max_q]

    if not eval_data:
        raise ValueError("Golden set is empty (no questions for this repository)")

    asset_repo_id = readiness.asset_repo_id

    health = check_index_health(asset_repo_id)
    health.raise_if_failed()
    if not settings.EVAL_SKIP_AGENT_PROBE:
        check_agent_probe(asset_repo_id).raise_if_failed()

    require_groq_quota()

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    ground_truths: list[str] = []

    total_confidence = 0.0
    total_precision_at_3 = 0.0
    gated_count = 0
    empty_source_count = 0
    sentinel_context_count = 0
    rate_limited_count = 0
    per_question: list[dict[str, Any]] = []
    state_path_failures: list[dict[str, Any]] = []

    print(f"Running golden set ({len(eval_data)} questions) via POST /chat on {asset_repo_id}...")

    for i, case in enumerate(eval_data):
        if i > 0:
            eval_question_delay()

        question = case["question"]
        case_repo = case.get("repo_id", job_id)
        _, case_asset = resolve_asset_repo_id(case_repo)
        chat_repo = case_asset or asset_repo_id

        paths: list[list[str]] = []
        res: dict[str, Any] = {}
        for run_idx in range(max(1, int(settings.EVAL_STATE_PATH_RUNS))):
            if i > 0 or run_idx > 0:
                eval_question_delay()
            res = _invoke_chat_endpoint(chat_repo, question)
            paths.append(_extract_state_path(res))

        consistent = all(p == paths[0] for p in paths[1:])
        state_path = paths[0] if paths else []
        if not consistent:
            state_path_failures.append({
                "question": question,
                "repo_id": chat_repo,
                "observed_paths": paths,
                "message": "State-transition sequence differed across repeated runs",
            })

        ans_text = res.get("answer", "")
        if res.get("rate_limited") or "rate-limited" in ans_text.lower():
            rate_limited_count += 1

        ctx_list, used_sentinel = build_ragas_contexts(res)
        if used_sentinel:
            sentinel_context_count += 1
        if res.get("gated"):
            gated_count += 1
        if not res.get("sources"):
            empty_source_count += 1

        gt_files = case.get("ground_truth_files", [])
        p_at_3, top_files, gt_hit = precision_at_k(res, gt_files, k=3)
        total_precision_at_3 += p_at_3
        total_confidence += float(res.get("confidence_score") or 0.0)

        pq = {
            "question": question,
            "repo_id": chat_repo,
            "expected_citations": gt_files,
            "precision_at_3": round(p_at_3, 4),
            "top_files": top_files,
            "ground_truth_files": gt_files,
            "gt_hit": gt_hit,
            "hit": gt_hit,
            "gated": bool(res.get("gated")),
            "confidence_score": round(float(res.get("confidence_score") or 0.0), 4),
            "context_count": len(ctx_list),
            "used_sentinel": used_sentinel,
            "rate_limited": bool(res.get("rate_limited")),
            "state_path": state_path,
            "state_path_consistent": consistent,
        }
        per_question.append(pq)

        questions.append(question)
        answers.append(ans_text)
        contexts.append(ctx_list)
        ground_truths.append(case.get("ground_truth_answer_summary", ""))

    n = len(eval_data)
    if rate_limited_count > 0:
        raise EvalPipelineError(
            f"Evaluation aborted: Groq quota exhausted ({rate_limited_count}/{n} rate-limited).",
            diagnostics={"rate_limited_count": rate_limited_count, "question_count": n},
        )

    gated_regressions = _flag_gated_regressions(per_question, eval_data)

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    judge_llm = get_judge_llm()
    judge_embeddings = get_judge_embeddings()
    eval_kwargs: dict[str, Any] = {"llm": judge_llm, "embeddings": judge_embeddings}
    if RunConfig is not None:
        eval_kwargs["run_config"] = RunConfig(
            timeout=int(settings.EVAL_RAGAS_TIMEOUT_S),
            max_retries=4,
            max_wait=120,
            max_workers=1,
        )

    metrics_list = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    ragas_judge_cooldown()
    ragas_result = None
    last_ragas_err: Exception | None = None
    for attempt in range(3):
        try:
            ragas_result = _run_ragas_evaluate(
                dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                **eval_kwargs,
            )
            break
        except Exception as exc:
            last_ragas_err = exc
            err = str(exc).lower()
            if "429" not in err and "rate" not in err:
                raise
            if attempt < 2:
                wait_s = 90 * (attempt + 1)
                print(f"RAGAS judge rate-limited — cooling down {wait_s}s before retry…")
                time.sleep(wait_s)
                ragas_judge_cooldown()
    if ragas_result is None:
        raise EvalPipelineError(
            f"RAGAS judge failed after retries: {last_ragas_err}",
            diagnostics={
                "rate_limited_count": rate_limited_count,
                "question_count": n,
                "chat_phase_complete": True,
            },
        ) from last_ragas_err

    ragas_scores = _extract_ragas_scores(ragas_result, metrics_list)
    row_scores = _per_row_ragas_scores(ragas_result, metrics_list)
    for pq, rs in zip(per_question, row_scores):
        pq["ragas_scores"] = rs

    state_passed = sum(1 for pq in per_question if pq.get("state_path_consistent"))
    aggregate = {
        "ragas_scores": ragas_scores,
        "mean_confidence_score": total_confidence / n,
        "retrieval_precision_at_3": total_precision_at_3 / n,
        "state_path_consistency_rate": state_passed / n if n else 0.0,
        "state_path_consistency_passed": state_passed,
        "state_path_consistency_total": n,
        "gated_count": gated_count,
    }

    regression_flags = {
        "gated_flips": gated_regressions,
        "state_path_failures": state_path_failures,
    }

    version, git_sha = _git_version()
    run_id = uuid.uuid4().hex

    report: dict[str, Any] = {
        "run_id": run_id,
        "repo_id": job_id,
        "version": version,
        "git_sha": git_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "golden_set_path": str(path),
        "per_question": per_question,
        "aggregate": aggregate,
        "ragas_scores": ragas_scores,
        "mean_confidence_score": aggregate["mean_confidence_score"],
        "retrieval_precision_at_3": aggregate["retrieval_precision_at_3"],
        "state_path_consistency": {
            "passed": state_passed,
            "total": n,
            "rate": aggregate["state_path_consistency_rate"],
            "failures": state_path_failures,
        },
        "regression_flags": regression_flags,
        "diagnostics": {
            "job_id": job_id,
            "asset_repo_id": asset_repo_id,
            "question_count": n,
            "gated_count": gated_count,
            "empty_source_count": empty_source_count,
            "sentinel_context_count": sentinel_context_count,
            "per_question": per_question,
            "gated_regressions": gated_regressions,
            "state_path_failures": state_path_failures,
        },
    }

    is_failure, failure_reason = diagnose_pipeline_failure(
        ragas_scores,
        question_count=n,
        gated_count=gated_count,
        empty_source_count=empty_source_count,
        sentinel_context_count=sentinel_context_count,
        retrieval_precision_at_3=total_precision_at_3 / n,
        mean_confidence=total_confidence / n,
    )
    if is_failure:
        raise EvalPipelineError(
            f"Evaluation aborted: pipeline failure — {failure_reason}",
            diagnostics={**report["diagnostics"], "ragas_scores": ragas_scores},
        )

    append_run(report)

    baseline = _find_comparable_baseline(load_runs(), n)
    if baseline:
        ragas_regressions = _check_ragas_regressions(
            baseline.get("ragas_scores", {}),
            ragas_scores,
        )
        if ragas_regressions:
            msg = "RAGAS regression detected:\n" + "\n".join(ragas_regressions)
            report["regression_warning"] = msg
            report["regression_baseline_version"] = baseline.get("version")
            update_last_run({
                "regression_warning": msg,
                "regression_baseline_version": baseline.get("version"),
            })

    if gated_regressions or state_path_failures:
        report["manual_review_required"] = True
        parts = []
        if gated_regressions:
            parts.append(f"{len(gated_regressions)} gated flip(s)")
        if state_path_failures:
            parts.append(f"{len(state_path_failures)} state-path failure(s)")
        report["regression_warning"] = report.get("regression_warning", "") + (
            "\nManual review: " + ", ".join(parts)
        ).strip()

    return report


def _git_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parent.parent
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL
        ).decode().strip()
        git_short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return settings.EVAL_VERSION or "unknown", "unknown"
    version = settings.EVAL_VERSION or (
        f"{git_short}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        if git_short != "unknown"
        else f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    return version, git_sha


def run_eval(
    dataset_path: str | None = None,
    *,
    target_repo_id: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias — delegates to ``run_golden_set()``."""
    path = Path(dataset_path) if dataset_path else None
    return run_golden_set(path, target_repo_id=target_repo_id)


if __name__ == "__main__":
    import sys

    try:
        _repo = os.environ.get("EVAL_TARGET_REPO_ID") or (
            sys.argv[1] if len(sys.argv) > 1 else None
        )
        result = run_golden_set(target_repo_id=_repo)
        print(json.dumps(result, indent=2, default=str))
        if result.get("manual_review_required"):
            print("\n[WARN] Manual review required — see regression_flags")
        if result.get("regression_warning"):
            print(f"\n[WARN] {result['regression_warning']}")
    except RegressionError as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)
    except EvalPipelineError as exc:
        print(f"\n[PIPELINE FAIL] {exc}")
        sys.exit(2)
    except GroqQuotaError as exc:
        print(f"\n[QUOTA BLOCKED] {exc}")
        sys.exit(3)
