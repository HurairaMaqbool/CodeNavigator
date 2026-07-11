"""Regression chat check for verification fix."""
from __future__ import annotations

import json
import time
import urllib.error
from urllib import request

from scripts._bootstrap import settings

api_key = settings.API_KEY
base_url = settings.API_BASE_URL.rstrip("/")
repo = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
QUESTION_DELAY_S = max(20.0, float(settings.EVAL_QUESTION_DELAY_S))

QUESTIONS = [
    "How does connection pooling improve performance?",
    "What happens internally when requests.get(url) is called?",
    "How request parameters are validated and processed",
    "The role of urllib3.PoolManager",
    "How does Session.send dispatch an HTTP request?",
]


def _post_chat(question: str, *, max_attempts: int = 4) -> tuple[dict | None, str | None]:
    body = json.dumps({"repo_id": repo, "question": question}).encode()
    last_err: str | None = None
    for attempt in range(max_attempts):
        req = request.Request(
            f"{base_url}/chat",
            data=body,
            method="POST",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode()), None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            last_err = f"HTTP {exc.code}: {raw[:300]}"
            if exc.code in (429, 504) and attempt + 1 < max_attempts:
                retry_after = 30
                try:
                    retry_after = int(exc.headers.get("Retry-After", retry_after))
                except (TypeError, ValueError):
                    pass
                wait = retry_after + 3 if exc.code == 429 else 10
                print(f"  retry {attempt + 2}/{max_attempts} after {wait}s ({exc.code})")
                time.sleep(wait)
                continue
            return None, last_err
        except Exception as exc:
            last_err = str(exc)
            if attempt + 1 < max_attempts:
                time.sleep(8)
                continue
            return None, last_err
    return None, last_err


def main() -> None:
    results = []
    for i, q in enumerate(QUESTIONS):
        if i > 0:
            print(f"  (waiting {QUESTION_DELAY_S:.0f}s before next question — TPM budget)\n")
            time.sleep(QUESTION_DELAY_S)
        t0 = time.time()
        data, err = _post_chat(q)
        elapsed = time.time() - t0
        if data is None:
            print(f"FAIL HTTP ({elapsed:.1f}s): {q}\n  {err}\n")
            results.append((q, False, err or ""))
            continue
        gated = bool(data.get("gated"))
        ans = data.get("answer") or ""
        ok = not gated and len(ans) > 80 and "could not verify" not in ans.lower()
        results.append((q, ok, ans[:300]))
        print(f"{'PASS' if ok else 'FAIL'} ({elapsed:.1f}s) gated={gated} score={data.get('confidence_score')}")
        print(f"  Q: {q}")
        print(f"  A: {ans[:280]!r}\n")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"SUMMARY: {passed}/{len(results)} passed")


if __name__ == "__main__":
    main()
