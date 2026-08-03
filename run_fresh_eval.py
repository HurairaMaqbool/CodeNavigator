from dotenv import load_dotenv
load_dotenv(override=True)

import os, json
key = os.environ.get("GROQ_API_KEY", "NOT SET")
print(f"Using key: {key[:20]}...")

from eval.run_eval import run_golden_set

print("=== FRESH RAGAS EVALUATION (new API key + strictness=1 fix) ===")
try:
    result = run_golden_set(
        target_repo_id="5749924cb6a9850057686b664b4b980fc407af109104df6f0aec8ec8182a4338"
    )
    rs = result.get("ragas_scores", {})
    avg = round(sum(rs.values()) / len(rs), 4) if rs else None
    print("=== FINAL RAGAS SCORES ===")
    for k, v in rs.items():
        print(f"  {k}: {round(v, 4)}")
    print(f"  AVERAGE: {avg}")
    print(f"Run ID: {result.get('run_id')}")
    print(f"Version: {result.get('version')}")
    print(f"Timestamp: {result.get('timestamp')}")
except Exception as exc:
    print(f"ERROR: {exc}")
    import traceback
    traceback.print_exc()
