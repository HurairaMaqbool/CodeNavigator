"""3-run repro for urllib3 latency + requests.get request_url verification."""
from __future__ import annotations

import re
import time

from app.agent.loop import _EXACT_QUESTION_CACHE, run

REPO = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"

QUERIES = [
    "Why does Requests use urllib3?",
    "What happens internally when requests.get(url) is called?",
    "How are retries and timeouts handled?",
]


def _cites(answer: str) -> list[str]:
    return re.findall(r"`[^`]+:\d+(?:-\d+)?`", answer or "")


def run_query(q: str, n: int = 3) -> list[dict]:
    rows = []
    for i in range(n):
        _EXACT_QUESTION_CACHE.clear()
        t0 = time.monotonic()
        r = run(REPO, q, job_id=JOB)
        elapsed = time.monotonic() - t0
        ans = r.get("answer") or ""
        timing = r.get("timing") or {}
        rows.append({
            "run": i + 1,
            "elapsed_s": round(elapsed, 1),
            "total_ms": timing.get("total_ms"),
            "retrieval_ms": timing.get("retrieval_ms"),
            "generation_ms": timing.get("generation_ms"),
            "verify_ms": timing.get("verify_ms"),
            "rate_limit_sleep_ms": timing.get("rate_limit_sleep_ms"),
            "facts": len(_cites(ans)),
            "gated": r.get("gated"),
            "timed_out": r.get("timed_out"),
            "rate_limited": r.get("rate_limited"),
            "request_url": "request_url" in ans.lower(),
            "preview": ans[:160].replace("\n", " "),
        })
        if i < n - 1:
            time.sleep(8)
    return rows


def main() -> None:
    for q in QUERIES:
        print("\n" + "=" * 72)
        print("QUERY:", q)
        print("=" * 72)
        rows = run_query(q, 3)
        times = [r["elapsed_s"] for r in rows]
        under_20 = all(t <= 20 for t in times)
        print(f"All runs <= 20s: {under_20}  times={times}")
        for r in rows:
            print(
                f"  Run {r['run']}: {r['elapsed_s']}s facts={r['facts']} "
                f"ret={r['retrieval_ms']}ms gen={r['generation_ms']}ms "
                f"verify={r['verify_ms']}ms sleep={r['rate_limit_sleep_ms']}ms "
                f"gated={r['gated']} timeout={r['timed_out']} rl={r['rate_limited']} "
                f"request_url={r['request_url']}"
            )
            print(f"    {r['preview']}...")


if __name__ == "__main__":
    main()
