"""3-run repro for urllib3 latency + requests.get request_url verification."""
from __future__ import annotations

import re
import time

from app.agent.loop import _EXACT_QUESTION_CACHE, _ensure_models_warmed, run

REPO = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"

QUERIES = [
    "Why does Requests use urllib3?",
    "What happens internally when requests.get(url) is called?",
]


def main() -> None:
    _ensure_models_warmed()
    for q in QUERIES:
        print("=" * 60)
        print("QUERY:", q)
        times: list[float] = []
        for i in range(3):
            _EXACT_QUESTION_CACHE.clear()
            t0 = time.monotonic()
            r = run(REPO, q, job_id=JOB)
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            ans = r.get("answer") or ""
            cites = re.findall(r"`[^`]+:\d+(?:-\d+)?`", ans)
            tm = r.get("timing") or {}
            print(
                f"Run {i + 1}: {elapsed:.1f}s facts={len(cites)} "
                f"gated={r.get('gated')} timeout={r.get('timed_out')} "
                f"rl={r.get('rate_limited')} total_ms={tm.get('total_ms')} "
                f"sleep_ms={tm.get('rate_limit_sleep_ms')}"
            )
            if "request_url" in ans.lower():
                print("  request_url cited: YES")
            print(" ", ans[:140].replace("\n", " "))
            if i < 2:
                time.sleep(40)
        print(f"All <= 25s: {all(t <= 25 for t in times)}  times={[round(t, 1) for t in times]}")
        print()


if __name__ == "__main__":
    main()
