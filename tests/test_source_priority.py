# Copyright (c) 2026 Huraira Maqbool
from app.retrieval.source_priority import (
    is_reasoning_query,
    is_test_path,
    prefer_implementation_hits,
    source_path_penalty,
)


def test_test_path_detection():
    assert is_test_path("tests/test_requests.py")
    assert is_test_path("src/requests/sessions.py") is False


def test_source_penalty_tests():
    assert source_path_penalty("tests/foo.py") < -0.5
    assert source_path_penalty("src/foo.py") > 0


def test_prefer_implementation_drops_tests():
    hits = [
        {"chunk_metadata": {"display_path": "tests/test_x.py", "start_line": 1, "end_line": 5}},
        {"chunk_metadata": {"display_path": "src/requests/sessions.py", "start_line": 10, "end_line": 20}},
    ]
    out = prefer_implementation_hits(hits, "How are cookies persisted?")
    paths = [h["chunk_metadata"]["display_path"] for h in out]
    assert "src/requests/sessions.py" in paths
    assert "tests/test_x.py" not in paths


def test_reasoning_query_classifier():
    assert is_reasoning_query("Why does Requests use urllib3 instead of implementing HTTP from scratch?")
    assert is_reasoning_query("What is the purpose of Session?")
    assert is_reasoning_query("How are cookies persisted?") is False


from app.agent.grounding import (
    dedupe_claims,
    drop_coarse_citations,
    ensure_reasoning_claims,
    narrow_claims_to_chunks,
    polish_claims,
    clamp_claims_to_manifest,
)


def test_narrow_claims_snaps_to_method_chunk():
    chunks = [
        {
            "chunk": "def __init__(self, max_retries=DEFAULT_RETRIES):",
            "chunk_metadata": {
                "display_path": "src/requests/adapters.py",
                "file_path": "src/requests/adapters.py",
                "function_name": "__init__",
                "start_line": 201,
                "end_line": 221,
            },
        },
        {
            "chunk": "def send(self, request, stream=False, timeout=None): conn.urlopen retries",
            "chunk_metadata": {
                "display_path": "src/requests/adapters.py",
                "file_path": "src/requests/adapters.py",
                "function_name": "send",
                "start_line": 634,
                "end_line": 706,
            },
        },
    ]
    claims = [{
        "claim": "HTTPAdapter.send calls conn.urlopen with retries=self.max_retries.",
        "citation": {"file_path": "src/requests/adapters.py", "start_line": 158, "end_line": 221},
    }]
    out = narrow_claims_to_chunks(claims, chunks)
    cit = out[0]["citation"]
    assert cit["start_line"] == 634
    assert cit["end_line"] == 706


def test_polish_claims_drops_test_citations():
    chunks = [{
        "chunk": "merge_cookies session cookies",
        "chunk_metadata": {
            "display_path": "src/requests/sessions.py",
            "file_path": "src/requests/sessions.py",
            "function_name": "prepare_request",
            "start_line": 511,
            "end_line": 555,
        },
    }]
    claims = [
        {"claim": "Wrong from test.", "citation": {"file_path": "tests/test_requests.py", "start_line": 1, "end_line": 2}},
        {"claim": "Session merges cookies via merge_cookies.", "citation": {"file_path": "src/requests/sessions.py", "start_line": 511, "end_line": 555}},
    ]
    out = polish_claims(claims, chunks, "How are cookies persisted?")
    paths = [c["citation"]["file_path"] for c in out if c.get("citation")]
    assert "tests/test_requests.py" not in paths
    assert "src/requests/sessions.py" in paths


def test_ensure_reasoning_claims_prepends_doc_rationale():
    chunks = [{
        "chunk": "## Supported Features\n- Keep-Alive & Connection Pooling\n- Sessions with Cookie Persistence",
        "chunk_metadata": {
            "display_path": "README.md",
            "file_path": "README.md",
            "start_line": 1,
            "end_line": 56,
        },
    }]
    claims = [{
        "claim": "HTTPAdapter uses PoolManager.",
        "citation": {"file_path": "src/requests/adapters.py", "start_line": 239, "end_line": 267},
    }]
    q = "Why does Requests use urllib3 instead of implementing HTTP from scratch?"
    out = ensure_reasoning_claims(claims, chunks, q)
    assert out[0]["citation"]["file_path"] == "README.md"
    assert "connection pooling" in out[0]["claim"].lower() or "keep-alive" in out[0]["claim"].lower()


def test_drop_coarse_citations_snaps_class_span():
    chunks = [
        {
            "chunk": "class BaseAdapter: ...",
            "chunk_metadata": {
                "display_path": "src/requests/adapters.py",
                "file_path": "src/requests/adapters.py",
                "function_name": "BaseAdapter",
                "start_line": 158,
                "end_line": 221,
            },
        },
        {
            "chunk": "def __init__(self, max_retries=DEFAULT_RETRIES):",
            "chunk_metadata": {
                "display_path": "src/requests/adapters.py",
                "file_path": "src/requests/adapters.py",
                "function_name": "__init__",
                "start_line": 201,
                "end_line": 221,
            },
        },
        {
            "chunk": "def send(self, request): conn.urlopen retries",
            "chunk_metadata": {
                "display_path": "src/requests/adapters.py",
                "file_path": "src/requests/adapters.py",
                "function_name": "send",
                "start_line": 634,
                "end_line": 706,
            },
        },
    ]
    claims = [{
        "claim": "HTTPAdapter stores max_retries as a urllib3 Retry instance.",
        "citation": {"file_path": "src/requests/adapters.py", "start_line": 158, "end_line": 221},
    }]
    out = drop_coarse_citations(claims, chunks)
    cit = out[0]["citation"]
    assert cit["start_line"] == 201
    assert cit["end_line"] == 221


def test_clamp_claims_to_manifest_snaps_unknown_lines():
    chunks = [
        {
            "chunk": "def send(self, request): conn.urlopen",
            "chunk_metadata": {
                "display_path": "src/requests/adapters.py",
                "file_path": "src/requests/adapters.py",
                "function_name": "send",
                "start_line": 634,
                "end_line": 706,
            },
        },
    ]
    claims = [{
        "claim": "HTTPAdapter.send calls conn.urlopen with retries.",
        "citation": {"file_path": "src/requests/adapters.py", "start_line": 158, "end_line": 221},
    }]
    out = clamp_claims_to_manifest(claims, chunks)
    cit = out[0]["citation"]
    assert cit["start_line"] == 634
    assert cit["end_line"] == 706


def test_dedupe_claims_removes_redundant():
    claims = [
        {"claim": "HTTPAdapter uses PoolManager for connection pooling.", "citation": {"file_path": "a.py", "start_line": 1, "end_line": 2}},
        {"claim": "HTTPAdapter uses PoolManager for HTTP connection pooling.", "citation": {"file_path": "a.py", "start_line": 3, "end_line": 4}},
        {"claim": "Session merges cookies via merge_cookies.", "citation": {"file_path": "b.py", "start_line": 5, "end_line": 6}},
    ]
    out = dedupe_claims(claims, overlap_threshold=0.55)
    assert len(out) == 2