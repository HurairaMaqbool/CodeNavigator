"""Side-by-side /status vs /eval/health for the same repo_id (evidence script)."""
from __future__ import annotations

import json
import urllib.request

from scripts._bootstrap import settings

JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"


def _get(path: str) -> dict:
    req = urllib.request.Request(
        f"{settings.API_BASE_URL.rstrip('/')}{path}",
        headers={"X-API-Key": settings.API_KEY},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def main() -> None:
    st = _get(f"/status/{JOB}")
    eh = _get(f"/eval/health/{JOB}?probe_agent=false")
    print("=== SAME repo_id ===")
    print(JOB)
    print("\n=== /status ===")
    print(json.dumps({
        "ready": st.get("ready"),
        "status": st.get("status"),
        "sync_status": st.get("sync_status"),
        "files_parsed": st.get("files_parsed"),
        "chunks_created": st.get("chunks_created"),
        "asset_repo_id": st.get("asset_repo_id"),
    }, indent=2))
    print("\n=== /eval/health ===")
    print(json.dumps({
        "ok": eh.get("ok"),
        "errors": eh.get("errors"),
        "details": eh.get("details"),
    }, indent=2))
    print("\n=== AGREEMENT ===")
    print("PASS" if st.get("ready") and eh.get("ok") else "FAIL")


if __name__ == "__main__":
    main()
