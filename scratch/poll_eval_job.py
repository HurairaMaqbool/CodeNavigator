import json, time, urllib.request
from scripts._bootstrap import settings
base = settings.API_BASE_URL.rstrip("/")
headers = {"X-API-Key": settings.API_KEY}
jid = "509e8277200a4dcfa63e9ea486e817e6"
for i in range(12):
    req = urllib.request.Request(f"{base}/eval/status/{jid}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        st = json.loads(r.read())
    print(i, st.get("status"), (st.get("error") or "")[:120])
    if st.get("status") in ("done", "error"):
        break
    time.sleep(10)
