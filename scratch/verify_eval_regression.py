"""Poll eval job + verify compare with two runs."""
import json
import time
import urllib.error
import urllib.request

from scripts._bootstrap import settings

JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
base = settings.API_BASE_URL.rstrip("/")
headers = {"X-API-Key": settings.API_KEY, "Content-Type": "application/json"}


def get(path: str) -> dict:
    req = urllib.request.Request(f"{base}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def post(path: str, params: str = "") -> dict:
    url = f"{base}{path}{params}"
    req = urllib.request.Request(url, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def poll_eval(eval_job_id: str, timeout_s: int = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = get(f"/eval/status/{eval_job_id}")
        if st.get("status") in ("done", "error"):
            return st
        time.sleep(5)
    return {"status": "timeout"}


def main() -> None:
    print("=== eval health ===")
    eh = get(f"/eval/health/{JOB}?probe_agent=false")
    print("ok=", eh.get("ok"), "errors=", eh.get("errors"))

    print("\n=== start eval run 1 ===")
    j1 = post("/eval/run", f"?repo_id={JOB}")
    print(j1)
    r1 = poll_eval(j1["job_id"])
    print("run1 status:", r1.get("status"), "error:", r1.get("error"))

    print("\n=== start eval run 2 ===")
    j2 = post("/eval/run", f"?repo_id={JOB}")
    print(j2)
    r2 = poll_eval(j2["job_id"])
    print("run2 status:", r2.get("status"), "error:", r2.get("error"))

    hist = get("/eval/history")
    print("\n=== history count ===", len(hist))
    if len(hist) >= 2:
        v0 = hist[0].get("version")
        v1 = hist[1].get("version")
        print("compare", v0, "vs", v1)
        payload = json.dumps({
            "baseline_version": v0,
            "candidate_version": v1,
            "tolerance": 0.05,
        }).encode()
        req = urllib.request.Request(
            f"{base}/eval/compare",
            data=payload,
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            diff = json.loads(r.read())
        print("regressions_found:", diff.get("regressions_found"))
        print("regressions count:", len(diff.get("regressions") or []))


if __name__ == "__main__":
    main()
