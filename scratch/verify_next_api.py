"""Verify Next.js API layer against live backend."""
import json
import urllib.request

BASE = "http://localhost:8000"
KEY = "dev-secret-key"
JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
H = {"X-API-Key": KEY}


def get(path: str):
    req = urllib.request.Request(f"{BASE}{path}", headers=H)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read())


results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} | {name}" + (f" | {detail}" if detail else ""))


try:
    s, b = get("/health")
    check("GET /health", s == 200 and b.get("status") == "ok", str(b))
except Exception as e:
    check("GET /health", False, str(e))

try:
    s, b = get(f"/status/{JOB}")
    check("/status ready", b.get("ready") is True, f"sync={b.get('sync_status')} files={b.get('files_parsed')}")
except Exception as e:
    check("/status", False, str(e))

try:
    s, b = get(f"/eval/health/{JOB}?probe_agent=false")
    check("/eval/health", b.get("ok") is True, f"errors={b.get('errors')}")
except Exception as e:
    check("/eval/health", False, str(e))

try:
    s, b = get("/eval/history")
    check("/eval/history", isinstance(b, list), f"count={len(b)}")
except Exception as e:
    check("/eval/history", False, str(e))

try:
    s, b = get("/eval/golden-status")
    check("/eval/golden-status", "status" in b, b.get("status", ""))
except Exception as e:
    check("/eval/golden-status", False, str(e))

try:
    s, b = get("/platform/usage")
    check("/platform/usage", "org_id" in b, b.get("org_id", ""))
except Exception as e:
    check("/platform/usage", False, str(e))

try:
    fn = urllib.parse.quote("Session.send", safe="")
    s, b = get(f"/diagram/{JOB}/{fn}?depth=2")
    check("GET /diagram", not b.get("empty", True) or bool(b.get("mermaid")), f"empty={b.get('empty')}")
except Exception as e:
    check("GET /diagram", False, str(e))

import urllib.parse

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n=== API: {passed}/{len(results)} passed ===")
