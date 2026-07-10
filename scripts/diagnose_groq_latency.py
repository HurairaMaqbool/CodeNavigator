"""Groq latency regression — reports wall-clock, gating, and log evidence."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

QUESTIONS = [
    "The role of urllib3.PoolManager",
    "How request parameters are validated and processed",
    "What does requests.Session do",
    "Explain HTTPAdapter in requests",
    "Where is timeout configured in requests",
]


def main() -> None:
    from urllib import request

    cfg = dotenv_values(ROOT / ".env")
    api_key = cfg.get("API_KEY") or os.environ.get("API_KEY", "dev-secret-key")
    repo = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"

    print("=== Groq latency regression ===\n")
    results = []
    for q in QUESTIONS:
        body = json.dumps({"repo_id": repo, "question": q}).encode()
        req = request.Request(
            "http://localhost:8000/chat",
            data=body,
            method="POST",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        )
        t0 = time.time()
        try:
            with request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            elapsed = time.time() - t0
            ok = not data.get("gated") and bool(data.get("answer"))
            preview = (data.get("answer") or "")[:120]
            results.append({
                "question": q,
                "elapsed_s": round(elapsed, 1),
                "gated": data.get("gated"),
                "ok": ok,
                "sources": len(data.get("sources") or []),
                "preview": preview,
            })
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {elapsed:.1f}s gated={data.get('gated')} | {q}")
            print(f"       {preview!r}\n")
        except Exception as exc:
            elapsed = time.time() - t0
            results.append({"question": q, "elapsed_s": round(elapsed, 1), "ok": False, "error": str(exc)})
            print(f"[ERROR] {elapsed:.1f}s | {q}: {exc}\n")

    passed = sum(1 for r in results if r.get("ok"))
    print(f"Summary: {passed}/{len(results)} answered successfully")
    avg = sum(r["elapsed_s"] for r in results) / max(len(results), 1)
    print(f"Average wall-clock: {avg:.1f}s")


if __name__ == "__main__":
    main()
