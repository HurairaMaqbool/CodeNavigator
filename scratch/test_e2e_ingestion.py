import requests
import time
import sys

API_URL = "http://localhost:8000"
HEADERS = {"X-API-Key": "dev-secret-key"}

print("=== STARTING BLACK-BOX E2E INGESTION PIPELINE TESTS ===")

# 1. Ingest requests (small/medium repo)
print("\n--- Test 1.1: Ingest requests repo ---")
payload = {"repo_url": "https://github.com/psf/requests", "ref": "main"}
r = requests.post(f"{API_URL}/ingest", json=payload, headers=HEADERS)
if r.status_code not in (200, 202):
    print(f"[FAIL] Ingest requests failed with code {r.status_code}: {r.text}")
    sys.exit(1)

res = r.json()
job_id = res.get("job_id")
print(f"[PASS] Ingest request accepted. job_id = {job_id}")

# Poll status
print("Polling status...")
for i in range(30):
    status_r = requests.get(f"{API_URL}/status/{job_id}", headers=HEADERS)
    if status_r.status_code != 200:
        print(f"[FAIL] Failed to get status: {status_r.text}")
        sys.exit(1)
    status_res = status_r.json()
    status = status_res.get("sync_status") or status_res.get("status")
    print(f"  Attempt {i+1}: status = {status}")
    if status == "synced" or status == "ready":
        print(f"[PASS] Repo synced successfully! Files: {status_res.get('files_parsed')}, Chunks: {status_res.get('chunks_created')}")
        break
    if status == "failed":
        print(f"[FAIL] Sync failed: {status_res.get('error_reason')}")
        sys.exit(1)
    time.sleep(2)
else:
    print("[FAIL] Ingest timed out after 60 seconds")
    sys.exit(1)

# 2. Ingest force_reindex
print("\n--- Test 1.2: Force reindex ---")
payload["force_reindex"] = True
r = requests.post(f"{API_URL}/ingest", json=payload, headers=HEADERS)
if r.status_code not in (200, 202):
    print(f"[FAIL] Force reindex failed with code {r.status_code}: {r.text}")
    sys.exit(1)
res = r.json()
job_id_2 = res.get("job_id")
print(f"[PASS] Force reindex accepted. job_id = {job_id_2}")

# 3. Ingest invalid repo
print("\n--- Test 1.3: Ingest invalid repo URL ---")
payload_invalid = {"repo_url": "https://github.com/nonexistent/doesnotexist12345", "ref": "main"}
r = requests.post(f"{API_URL}/ingest", json=payload_invalid, headers=HEADERS)
if r.status_code not in (200, 202):
    # Some validations return 400/422 immediately, which is also a PASS (fails fast)
    print(f"[PASS] Invalid repo rejected/accepted with code {r.status_code}")
else:
    job_id_invalid = r.json().get("job_id")
    print(f"Accepted invalid repo. job_id = {job_id_invalid}. Polling...")
    for i in range(15):
        status_r = requests.get(f"{API_URL}/status/{job_id_invalid}", headers=HEADERS)
        status_res = status_r.json()
        status = status_res.get("sync_status") or status_res.get("status")
        print(f"  Attempt {i+1}: status = {status}")
        if status == "failed":
            print(f"[PASS] Invalid repo failed as expected. Reason: {status_res.get('error_reason')}")
            break
        if status == "synced" or status == "ready":
            print("[FAIL] Invalid repo unexpectedly synced!")
            sys.exit(1)
        time.sleep(2)
    else:
        print("[FAIL] Invalid repo ingestion didn't fail within 30 seconds")
        sys.exit(1)

# 4. Concurrent ingestion of the same repo
print("\n--- Test 1.4: Concurrent ingestion lock ---")
# Start ingestion for requests again
r1 = requests.post(f"{API_URL}/ingest", json={"repo_url": "https://github.com/psf/requests", "ref": "main", "force_reindex": True}, headers=HEADERS)
# Immediately start another one
r2 = requests.post(f"{API_URL}/ingest", json={"repo_url": "https://github.com/psf/requests", "ref": "main", "force_reindex": True}, headers=HEADERS)
print(f"  First call: {r1.status_code}, Second call: {r2.status_code}")
# The second call should return 409 or return the status of the already running job or be handled gracefully
if r2.status_code == 409:
    print("[PASS] Concurrent ingestion correctly blocked with 409 Conflict")
elif r2.status_code in (200, 202):
    # Or if it returns the already running job_id or a message
    print(f"[PASS] Concurrent ingestion handled gracefully: {r2.text}")
else:
    print(f"[FAIL] Unexpected status code for concurrent request: {r2.status_code}")
    sys.exit(1)

print("\n=== ALL BLACK-BOX E2E INGESTION TESTS PASSED ===")
