"""5-run consistency repro for HTTPAdapter + custom transport queries."""
from __future__ import annotations

import re
import sys
import time

from app.agent.loop import _EXACT_QUESTION_CACHE, run

REPO = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"

QUERIES = [
    "What does HTTPAdapter do?",
    "If you wanted to add a custom transport layer or retry mechanism, where would you make changes?",
]


def _fact_count(answer: str) -> int:
    cites = re.findall(r"`[^`]+:\d+(?:-\d+)?`", answer or "")
    return max(1, len(cites)) if cites else 0


def _citation_set(answer: str) -> frozenset[str]:
    return frozenset(re.findall(r"`[^`]+:\d+(?:-\d+)?`", answer or ""))


def run_suite(question: str, n: int = 5) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        _EXACT_QUESTION_CACHE.clear()
        t0 = time.monotonic()
        r = run(REPO, question, job_id=JOB)
        elapsed = time.monotonic() - t0
        ans = r.get("answer") or ""
        rows.append({
            "run": i + 1,
            "facts": _fact_count(ans),
            "citations": sorted(_citation_set(ans)),
            "cache_hit": r.get("cache_hit"),
            "gated": r.get("gated"),
            "timing": r.get("timing"),
            "elapsed_s": round(elapsed, 1),
            "preview": ans[:120].replace("\n", " "),
        })
    return rows


def main() -> None:
    for q in QUERIES:
        print("\n" + "=" * 72)
        print("QUERY:", q)
        print("=" * 72)
        rows = run_suite(q, 5)
        cite_sets = [frozenset(r["citations"]) for r in rows]
        fact_counts = [r["facts"] for r in rows]
        consistent = len(set(cite_sets)) == 1 and len(set(fact_counts)) == 1
        print(f"Consistent across 5 runs: {consistent}")
        for r in rows:
            print(
                f"  Run {r['run']}: facts={r['facts']} gated={r['gated']} "
                f"cache={r['cache_hit']} time={r['elapsed_s']}s "
                f"cites={len(r['citations'])}"
            )
            print(f"    {r['preview']}...")
        if not consistent:
            print("  Citation variance:")
            for i, cs in enumerate(cite_sets, 1):
                print(f"    Run {i}: {list(cs)[:4]}")


if __name__ == "__main__":
    main()
