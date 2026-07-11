"""Quick smoke: POST /eval/run with active repo_id."""
import json
import urllib.error
import urllib.request

from scripts._bootstrap import settings

JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
base = settings.API_BASE_URL.rstrip("/")
headers = {"X-API-Key": settings.API_KEY}

url = f"{base}/eval/run?repo_id={JOB}"
req = urllib.request.Request(url, method="POST", headers=headers)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
        print("POST /eval/run", r.status, body[:300])
except urllib.error.HTTPError as e:
    print("POST /eval/run FAILED", e.code, e.read()[:400].decode())

req2 = urllib.request.Request(f"{base}/eval/run", method="POST", headers=headers)
try:
    urllib.request.urlopen(req2, timeout=10)
except urllib.error.HTTPError as e:
    print("POST /eval/run no repo_id =>", e.code, "(expected 400)")
