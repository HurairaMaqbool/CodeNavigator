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

from app.agent.loop import answer_question
from app.observability.logging_config import logger
from app.repo_resolver import resolve_asset_repo_id
from eval.retrieval_metrics import collect_cited_files, paths_match as _paths_match

GOLDEN_SET_PATH = Path("tests/eval_set.json")
STATUS_PATH = Path("tests/golden_set_status.json")

TOP_K = 10
PASS_THRESHOLD = 0.80
GOLDEN_QUESTION_DELAY_S = 2.0


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

    total = 0
    passed = 0
    failed_questions: list[str] = []
    per_repo: dict[str, dict[str, Any]] = {}
    skipped_fixtures: list[str] = []

    for case in data:
        question = case["question"]
        job_id = case.get("repo_id")
        gt_files = case.get("ground_truth_files", [])
        fixture = case.get("fixture") or job_id[:16]
        if not job_id:
            continue

        meta, asset_repo_id = resolve_asset_repo_id(job_id)
        if not meta or meta.sync_status != "synced":
            logger.warning("golden_skip_unsynced", repo_id=job_id, question=question)
            if fixture not in skipped_fixtures:
                skipped_fixtures.append(fixture)
            continue

        repo_stats = per_repo.setdefault(
            fixture,
            {"fixture": fixture, "repo_id": job_id, "total": 0, "passed": 0},
        )

        total += 1
        repo_stats["total"] += 1
        if total > 1:
            time.sleep(GOLDEN_QUESTION_DELAY_S)
        try:
            res = answer_question(question, asset_repo_id)
        except Exception as exc:
            logger.error("golden_question_crashed", question=question, error=str(exc))
            failed_questions.append(question)
            continue

        cited_files = collect_cited_files(res, top_k=TOP_K)
        hit = any(_paths_match(f, gt) for f in cited_files for gt in gt_files)
        if hit:
            passed += 1
            repo_stats["passed"] += 1
        else:
            logger.warning(
                "golden_miss",
                question=question[:80],
                cited=cited_files[:3],
                expected=gt_files,
                gated=res.get("gated"),
            )
            failed_questions.append(question)

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
