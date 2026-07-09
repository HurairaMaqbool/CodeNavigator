# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
Compare baseline hybrid search vs symbol-boost prefetch on golden-set questions.

Does not call the LLM — retrieval-only, fast smoke for tuning retrieval.

Usage:
  python scripts/retrieval_ablation.py
  python scripts/retrieval_ablation.py --limit 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.loop import _hits_from_search_result, _reorder_hits_for_question
from app.agent.retrieval_prefetch import run_prefetch
from app.agent.tools import execute_tool_with_retry
from app.observability.logging_config import logger
from app.repo_resolver import resolve_asset_repo_id
from eval.retrieval_metrics import precision_at_k


def _baseline_prefetch(question: str, repo_id: str) -> list[dict]:
    result = execute_tool_with_retry("search_code", {"query": question, "top_k": 5}, repo_id)
    hits = _reorder_hits_for_question(question, _hits_from_search_result(result))
    return hits


def _enhanced_prefetch(question: str, repo_id: str) -> list[dict]:
    cache: dict = {}
    _, hits, _ = run_prefetch(
        question,
        repo_id,
        logger,
        hits_from_result=_hits_from_search_result,
        reorder_hits=_reorder_hits_for_question,
        tool_cache=cache,
    )
    return hits


def _hit_rate(hits: list[dict], gt_files: list[str], k: int = 3) -> tuple[float, list[str]]:
    fake_res = {"sources": [], "retrieval_hits": hits, "answer": ""}
    for h in hits[:k]:
        fp = h.get("file_path")
        if fp:
            fake_res["sources"].append({"file_path": fp})
    p, files, _ = precision_at_k(fake_res, gt_files, k=k)
    return p, files


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval ablation on golden set")
    parser.add_argument("--limit", type=int, default=0, help="Max questions (0 = all)")
    parser.add_argument("--dataset", default="tests/eval_set.json")
    args = parser.parse_args()

    data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    if args.limit > 0:
        data = data[: args.limit]

    baseline_p = 0.0
    enhanced_p = 0.0
    n = 0

    print(f"{'Question':<50} {'Base P@3':>9} {'Boost P@3':>10} {'Delta':>8}")
    print("-" * 82)

    for case in data:
        question = case["question"]
        job_id = case.get("repo_id")
        gt_files = case.get("ground_truth_files", [])
        if not job_id or not gt_files:
            continue

        _, asset_repo_id = resolve_asset_repo_id(job_id)
        base_hits = _baseline_prefetch(question, asset_repo_id)
        enh_hits = _enhanced_prefetch(question, asset_repo_id)

        bp, _ = _hit_rate(base_hits, gt_files)
        ep, _ = _hit_rate(enh_hits, gt_files)
        baseline_p += bp
        enhanced_p += ep
        n += 1

        delta = ep - bp
        print(f"{question[:48]:<50} {bp:9.2f} {ep:10.2f} {delta:+8.2f}")

    if not n:
        print("No questions evaluated (check repo sync status).")
        return 1

    print("-" * 82)
    print(f"Mean P@3  baseline={baseline_p / n:.3f}  enhanced={enhanced_p / n:.3f}  delta={(enhanced_p - baseline_p) / n:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
