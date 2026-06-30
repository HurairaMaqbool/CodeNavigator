import os
import sys
from pathlib import Path

# Insert project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["LLM_PROVIDER"] = "groq"

from app.agent.tools import _do_search_code

repo_id = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
query = "send HTTP request in Session class"

res = _do_search_code(repo_id, query, top_k=5)
for i, r in enumerate(res["results"]):
    print(f"\n--- Result {i+1} ---")
    print(f"File Path: {r.get('metadata', {}).get('file_path')}")
    print(f"Rerank Score: {r.get('rerank_score')}")
    print(f"Snippet: {r.get('chunk')[:200]}")
