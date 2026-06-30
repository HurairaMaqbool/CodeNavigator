import os
import json
import sys
from pathlib import Path

# Insert project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force Groq API key configuration
os.environ["LLM_PROVIDER"] = "groq"

from app.agent.loop import answer_question

repo_id = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
question = "Which file handles sending an HTTP request in the Session class?"

print("Running answer_question...")
res = answer_question(question, repo_id=repo_id)
print("\n--- RESPONSE DICT ---")
print(json.dumps(res, indent=2))
