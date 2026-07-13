"""5-run consistency repro for HTTPAdapter query only (with rate-limit spacing)."""
from __future__ import annotations

import re
import time

from app.agent.loop import _EXACT_QUESTION_CACHE, run

REPO = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
QUESTION = "What does HTTPAdapter do?"
SLEEP_S = 35


def _citation_set(answer: str) -> frozenset[str]:
    return frozenset(re.findall(r"`[^`]+:\d+(?:-\d+)?`", answer or ""))


def main() -> None:
    rows = []
    for i in range(5):
        _EXACT_QUESTION_CACHE.clear()
        t0 = time.monotonic()
        r = run(REPO, QUESTION, job_id=JOB)
        elapsed = time.monotonic() - t0
        ans = r.get("answer") or ""
        cites = sorted(_citation_set(ans))
        rows.append({
            "run": i + 1,
            "facts": len(cites) or 1,
            "citations": cites,
            "gated": r.get("gated"),
            "elapsed_s": round(elapsed, 1),
            "retrieval_hits": (r.get("timing") or {}).get("retrieval_hits"),
            "answer": ans,
        })
        if i < 4:
            time.sleep(SLEEP_S)

    cite_sets = [frozenset(r["citations"]) for r in rows]
    fact_counts = [r["facts"] for r in rows]
    consistent = len(set(cite_sets)) == 1 and len(set(fact_counts)) == 1
    print(f"Consistent across 5 runs: {consistent}")
    for r in rows:
        print(
            f"Run {r['run']}: facts={r['facts']} hits={r['retrieval_hits']} "
            f"gated={r['gated']} time={r['elapsed_s']}s"
        )
        print(f"  cites: {r['citations']}")
        print(f"  preview: {r['answer'][:200].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
