"""Quick live /chat latency + answer check."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import request

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
cfg = dotenv_values(ROOT / ".env")
api_key = cfg.get("API_KEY") or os.environ.get("API_KEY", "dev-secret-key")
repo = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
questions = [
    "How request parameters are validated and processed",
    "The role of urllib3.PoolManager",
]

for q in questions:
    body = json.dumps({"repo_id": repo, "question": q}).encode()
    req = request.Request(
        "http://localhost:8000/chat",
        data=body,
        method="POST",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    t0 = time.time()
    with request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    elapsed = time.time() - t0
    ans = (data.get("answer") or "")[:220]
    gated = data.get("gated")
    print(f"Q: {q}")
    print(f"  time={elapsed:.1f}s gated={gated} score={data.get('confidence_score')}")
    print(f"  sources={len(data.get('sources') or [])} respond_count="
          f"{sum(1 for t in data.get('trace', []) if t.get('state') == 'RESPOND')}")
    print(f"  preview={ans!r}")
    print()
