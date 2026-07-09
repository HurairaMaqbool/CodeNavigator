# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
Print per-question retrieval diagnostics from a stored eval run.

Usage:
  python scripts/eval_per_question_report.py
  python scripts/eval_per_question_report.py eval_20260627_190620
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.eval_store import get_run, load_runs


def _pick_run(version: str | None) -> dict | None:
    if version:
        return get_run(version)
    runs = load_runs(newest_first=True)
    return runs[0] if runs else None


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else None
    run = _pick_run(version)
    if not run:
        print("No eval runs found.")
        return 1

    diag = run.get("diagnostics") or {}
    rows = diag.get("per_question") or []
    if not rows:
        print(
            f"Run {run.get('version')} has no per_question diagnostics "
            "(re-run eval with the updated run_eval.py)."
        )
        return 1

    print(f"Eval run: {run.get('version')}  P@3={run.get('retrieval_precision_at_3', 0):.3f}")
    print("-" * 100)
    for i, row in enumerate(rows, 1):
        q = row.get("question", "")[:70]
        hit = "HIT" if row.get("gt_hit") else "MISS"
        print(
            f"{i:2}. [{hit}] P@3={row.get('precision_at_3', 0):.2f}  "
            f"gated={row.get('gated')}  conf={row.get('confidence_score', 0):.2f}"
        )
        print(f"    Q: {q}")
        print(f"    top: {', '.join(row.get('top_files') or []) or '(none)'}")
        print(f"    gt:  {', '.join(row.get('ground_truth_files') or [])}")
        print()

    out_path = Path("tests/eval_per_question_report.json")
    out_path.write_text(
        json.dumps({"version": run.get("version"), "per_question": rows}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
