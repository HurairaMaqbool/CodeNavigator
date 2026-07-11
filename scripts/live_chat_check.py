"""Quick live /chat latency + answer check."""
from __future__ import annotations

import json
import time
from urllib import request

from scripts._bootstrap import settings

api_key = settings.API_KEY
base_url = settings.API_BASE_URL.rstrip("/")
repo = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
questions = [
    "How request parameters are validated and processed",
    "The role of urllib3.PoolManager",
]

for q in questions:
    body = json.dumps({"repo_id": repo, "question": q}).encode()
    req = request.Request(
        f"{base_url}/chat",
        data=body,
        method="POST",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    t0 = time.time()
    with request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    elapsed = time.time() - t0
    print(f"({elapsed:.1f}s) gated={data.get('gated')} score={data.get('confidence_score')}")
    print(f"Q: {q}")
    print(f"A: {(data.get('answer') or '')[:200]!r}\n")
