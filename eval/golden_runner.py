# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/golden_runner.py
---------------------
Golden Set CI runner.

Unlike the RAGAS harness (eval/run_eval.py), which uses an LLM judge and is
slow/expensive, the Golden Set is a FAST, deterministic, LLM-judge-free gate:
for each known question it runs the real agent and checks whether at least one
ground-truth file appears in cited sources, retrieval hits, or the answer text.
File-level precision is a reliable, cheap signal for code QA and is what CI
should block on.

Status is written to tests/golden_set_status.json so the UI always reflects the
*current* agent state. This runner is invoked automatically after every
successful ingestion (see app/tasks/ingestion_task.py) and on demand via the
/eval/golden/run endpoint.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ingestion.repo_readiness import is_repo_ready
from app.observability.logging_config import logger
from eval.retrieval_metrics import collect_cited_files, paths_match as _paths_match
from eval.run_eval import EvalPipelineError, _invoke_chat_endpoint

GOLDEN_SET_PATH = Path("tests/eval_set.json")
STATUS_PATH = Path("tests/golden_set_status.json")

TOP_K = 15
PASS_THRESHOLD = 0.80
GOLDEN_RETRY_COOLDOWN_S = 60.0


def _golden_question_delay() -> None:
    """Longer pause than RAGAS eval — golden runs many agent calls back-to-back."""
    from app.config import settings

    delay = max(float(settings.EVAL_QUESTION_DELAY_S), 10.0)
    time.sleep(delay)


def _score_case(
    res: dict[str, Any],
    gt_files: list[str],
) -> tuple[bool, list[str]]:
    cited_files = collect_cited_files(res, top_k=TOP_K)
    hit = any(_paths_match(f, gt) for f in cited_files for gt in gt_files)
    return hit, cited_files


def _run_case(
    job_id: str,
    question: str,
    gt_files: list[str],
    fixture: str,
) -> tuple[bool, dict[str, Any] | None]:
    """Run one golden question; return (passed, failure_detail or None)."""
    try:
        res = _invoke_chat_endpoint(job_id, question)
    except (EvalPipelineError, Exception) as exc:
        logger.error("golden_question_crashed", question=question, error=str(exc))
        return False, {
            "question": question,
            "fixture": fixture,
            "expected_files": gt_files,
            "cited_files": [],
            "error": str(exc),
            "retryable": "429" in str(exc).lower() or "rate" in str(exc).lower(),
        }

    hit, cited_files = _score_case(res, gt_files)
    if hit:
        return True, None

    logger.warning(
        "golden_miss",
        question=question[:80],
        cited=cited_files[:3],
        expected=gt_files,
        gated=res.get("gated"),
    )
    return False, {
        "question": question,
        "fixture": fixture,
        "expected_files": gt_files,
        "cited_files": cited_files[:TOP_K],
        "gated": bool(res.get("gated")),
        "retryable": bool(res.get("rate_limited") or res.get("gated")),
    }


def run_golden_set(golden_path: str | Path = GOLDEN_SET_PATH) -> dict[str, Any]:
    """
    Run every golden question through the live agent and write a status file.

    Returns the status dict: {status, timestamp, score, total, passed,
    failed_questions}.
    """
    path = Path(golden_path)
    if not path.exists():
        raise FileNotFoundError(f"Golden set not found at {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    if not data:
        raise ValueError("Golden set is empty")

    cases: list[dict[str, Any]] = []
    skipped_fixtures: list[str] = []

    for case in data:
        question = case["question"]
        job_id = case.get("repo_id")
        gt_files = case.get("ground_truth_files", [])
        fixture = case.get("fixture") or (job_id[:16] if job_id else "unknown")
        if not job_id:
            continue

        readiness = is_repo_ready(job_id)
        if not readiness.ready:
            logger.warning(
                "golden_skip_unsynced",
                repo_id=job_id,
                question=question,
                status=readiness.sync_status,
            )
            if fixture not in skipped_fixtures:
                skipped_fixtures.append(fixture)
            continue

        cases.append(
            {
                "question": question,
                "job_id": job_id,
                "gt_files": gt_files,
                "fixture": fixture,
            }
        )

    per_repo: dict[str, dict[str, Any]] = {}
    results: list[tuple[bool, dict[str, Any] | None]] = []

    for i, case in enumerate(cases):
        if i > 0:
            _golden_question_delay()
        passed, detail = _run_case(
            case["job_id"],
            case["question"],
            case["gt_files"],
            case["fixture"],
        )
        results.append((passed, detail))
        stats = per_repo.setdefault(
            case["fixture"],
            {
                "fixture": case["fixture"],
                "repo_id": case["job_id"],
                "total": 0,
                "passed": 0,
            },
        )
        stats["total"] += 1
        if passed:
            stats["passed"] += 1

    # Retry failures once after cooldown (429 / gated / retrieval miss).
    retry_indices = [
        i
        for i, (ok, detail) in enumerate(results)
        if not ok and detail and detail.get("retryable", True)
    ]
    if retry_indices:
        logger.info("golden_retry_pass", count=len(retry_indices))
        time.sleep(GOLDEN_RETRY_COOLDOWN_S)
        for i in retry_indices:
            _golden_question_delay()
            case = cases[i]
            passed, detail = _run_case(
                case["job_id"],
                case["question"],
                case["gt_files"],
                case["fixture"],
            )
            if passed:
                results[i] = (True, None)
                per_repo[case["fixture"]]["passed"] += 1
            else:
                results[i] = (False, detail)

    total = len(results)
    passed = sum(1 for ok, _ in results if ok)
    failed_questions: list[str] = []
    failed_details: list[dict[str, Any]] = []
    for case, (ok, detail) in zip(cases, results):
        if not ok and detail:
            failed_questions.append(case["question"])
            failed_details.append(detail)

    for stats in per_repo.values():
        t = stats["total"]
        stats["score"] = round(stats["passed"] / t, 4) if t else 0.0

    score = (passed / total) if total else 0.0
    status = {
        "status": "pass" if score >= PASS_THRESHOLD else "fail",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": round(score, 4),
        "total": total,
        "passed": passed,
        "pass_threshold": PASS_THRESHOLD,
        "failed_questions": failed_questions,
        "failed_details": failed_details,
        "per_repo": list(per_repo.values()),
        "skipped_fixtures": skipped_fixtures,
        "fixture_count": len(per_repo),
    }

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    logger.info("golden_set_completed", status=status["status"], score=score, total=total)
    return status


if __name__ == "__main__":
    print(json.dumps(run_golden_set(), indent=2))
