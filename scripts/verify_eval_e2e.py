#!/usr/bin/env python3
# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
End-to-end Evaluation verification: precheck → Golden CI → optional RAGAS smoke.

Usage:
  python scripts/verify_eval_e2e.py
  python scripts/verify_eval_e2e.py --ragas --max-questions 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_JOB = os.environ.get(
    "EVAL_JOB_ID",
    "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluation e2e verification")
    parser.add_argument("--job-id", default=DEFAULT_JOB)
    parser.add_argument("--ragas", action="store_true", help="Run RAGAS eval (slow)")
    parser.add_argument("--max-questions", type=int, default=0, help="Limit RAGAS questions (0=all; use 3 for smoke)")
    parser.add_argument(
        "--skip-golden-if-fresh",
        action="store_true",
        help="Skip Golden re-run when tests/golden_set_status.json is pass and <6h old",
    )
    args = parser.parse_args()

    from eval.health_check import run_full_eval_precheck
    from eval.golden_runner import run_golden_set

    report: dict = {"job_id": args.job_id, "steps": []}

    pre = run_full_eval_precheck(args.job_id, include_agent_probe=False)
    pre_step = {
        "step": "eval_precheck",
        "ok": pre.ok,
        "details": pre.details,
        "errors": pre.errors,
    }
    report["steps"].append(pre_step)
    print(f"[1/3] Precheck: {'PASS' if pre.ok else 'FAIL'}")
    if not pre.ok:
        print(json.dumps(report, indent=2))
        return 1

    golden = None
    status_path = ROOT / "tests" / "golden_set_status.json"
    skip_golden = False
    if args.skip_golden_if_fresh and status_path.exists():
        try:
            cached = json.loads(status_path.read_text(encoding="utf-8"))
            ts = cached.get("timestamp")
            age_h = 999.0
            if ts:
                from datetime import datetime, timezone

                age_h = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ).total_seconds() / 3600.0
            if (
                cached.get("status") == "pass"
                and cached.get("passed") == cached.get("total")
                and age_h < 6.0
            ):
                skip_golden = True
                golden = cached
                print(
                    f"[2/3] Golden CI: cached PASS "
                    f"({golden.get('passed')}/{golden.get('total')}, age {age_h:.1f}h)"
                )
        except Exception:
            skip_golden = False

    if not skip_golden:
        golden = run_golden_set()
        print(
            f"[2/3] Golden CI: {golden.get('status')} "
            f"({golden.get('passed')}/{golden.get('total')} = {golden.get('score')})"
        )

    golden_step = {
        "step": "golden_ci",
        "status": golden.get("status") if golden else "fail",
        "score": golden.get("score"),
        "passed": golden.get("passed"),
        "total": golden.get("total"),
        "skipped_cached": skip_golden,
    }
    report["steps"].append(golden_step)
    if golden.get("status") != "pass":
        print(json.dumps(report, indent=2))
        return 2

    if args.ragas:
        from app.config import settings

        if args.max_questions > 0:
            os.environ["EVAL_MAX_QUESTIONS"] = str(args.max_questions)
            settings.EVAL_MAX_QUESTIONS = args.max_questions

        from eval.run_eval import run_golden_set as run_ragas_eval

        print("[3/3] RAGAS eval starting (may take several minutes)…")
        t0 = time.perf_counter()
        try:
            ragas = run_ragas_eval(target_repo_id=args.job_id)
        except Exception as exc:
            report["steps"].append({"step": "ragas", "ok": False, "error": str(exc)})
            print(json.dumps(report, indent=2))
            return 3

        elapsed = time.perf_counter() - t0
        scores = ragas.get("ragas_scores") or {}
        report["steps"].append(
            {
                "step": "ragas",
                "ok": bool(scores),
                "elapsed_s": round(elapsed, 1),
                "ragas_scores": scores,
                "mean_confidence": ragas.get("mean_confidence_score"),
            }
        )
        print(f"[3/3] RAGAS: {json.dumps(scores)} ({elapsed:.0f}s)")
    else:
        print("[3/3] RAGAS: skipped (pass --ragas to run)")

    out = ROOT / "eval_results" / "verify_eval_e2e_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
