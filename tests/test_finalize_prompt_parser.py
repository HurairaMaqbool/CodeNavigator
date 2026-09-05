import pytest
from app.agent.grounding import parse_finalize_json, strip_json_fences

def test_parse_normal_json():
    raw = '{"claims":[{"claim":"API key verification works","citation":{"file_path":"src/auth.py","start_line":10,"end_line":20}}]}'
    claims = parse_finalize_json(raw)
    assert len(claims) == 1
    assert claims[0]["claim"] == "API key verification works"
    assert claims[0]["citation"]["file_path"] == "src/auth.py"

def test_parse_json_after_think_block():
    raw = """<think>
I should analyze the codebase context carefully.
The ingestion lock is implemented in locking.py.
</think>
{"claims":[{"claim":"Ingestion lock prevents concurrent runs","citation":{"file_path":"app/ingestion/locking.py","start_line":15,"end_line":30}}]}"""
    claims = parse_finalize_json(raw)
    assert len(claims) == 1
    assert claims[0]["claim"] == "Ingestion lock prevents concurrent runs"
    assert claims[0]["citation"]["file_path"] == "app/ingestion/locking.py"

def test_parse_multiline_think_block():
    raw = """<think>
Line 1: Analyze question
Line 2: Search context
Line 3: Decompose claims
</think>

```json
{
  "claims": [
    {
      "claim": "Hybrid search uses RRF algorithm",
      "citation": {
        "file_path": "app/retrieval/hybrid_search.py",
        "start_line": 80,
        "end_line": 120
      }
    }
  ]
}
```"""
    claims = parse_finalize_json(raw)
    assert len(claims) == 1
    assert claims[0]["claim"] == "Hybrid search uses RRF algorithm"
    assert claims[0]["citation"]["file_path"] == "app/retrieval/hybrid_search.py"

def test_parse_invalid_json():
    raw = "<think>some thinking</think> {invalid json object"
    claims = parse_finalize_json(raw)
    assert claims == []

def test_parse_missing_json():
    raw = "<think>thinking only without json object</think>"
    claims = parse_finalize_json(raw)
    assert claims == []
