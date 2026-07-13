# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_8.py
----------------------
Module 8: LLM Provider Abstraction Tests
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mock groq SDK and httpx definitions
_MOCK_GROQ = MagicMock()
class GroqRateLimitError(Exception):
    def __init__(self, *args, **kwargs): pass
class APIStatusError(Exception): pass
class APITimeoutError(Exception): pass
_MOCK_GROQ.Groq = MagicMock
_MOCK_GROQ.RateLimitError = GroqRateLimitError
_MOCK_GROQ.APIStatusError = APIStatusError
_MOCK_GROQ.APITimeoutError = APITimeoutError

_MOCK_HTTPX = MagicMock()
class ConnectError(Exception): pass
class HTTPStatusError(Exception): 
    def __init__(self, message, request=None, response=None):
        self.response = response
_MOCK_HTTPX.Client = MagicMock
_MOCK_HTTPX.ConnectError = ConnectError
_MOCK_HTTPX.HTTPStatusError = HTTPStatusError

_orig_groq = None
_orig_httpx = None

def setUpModule():
    global _orig_groq, _orig_httpx
    _orig_groq = sys.modules.get("groq")
    _orig_httpx = sys.modules.get("httpx")
    sys.modules["groq"] = _MOCK_GROQ
    sys.modules["httpx"] = _MOCK_HTTPX

def tearDownModule():
    global _orig_groq, _orig_httpx
    if _orig_groq is not None:
        sys.modules["groq"] = _orig_groq
    else:
        sys.modules.pop("groq", None)
    if _orig_httpx is not None:
        sys.modules["httpx"] = _orig_httpx
    else:
        sys.modules.pop("httpx", None)

from app.observability.logging_config import configure_logging
configure_logging()

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# STEP 1: Confirm Deliverables
# ---------------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    from app.agent.llm_client import get_llm_client, GroqAdapter, OllamaAdapter
    
    assert_ok(callable(get_llm_client), "get_llm_client missing")
    assert_ok(hasattr(GroqAdapter, "create") and callable(GroqAdapter.create), "GroqAdapter.create missing")
    assert_ok(hasattr(OllamaAdapter, "create") and callable(OllamaAdapter.create), "OllamaAdapter.create missing")
    
    # Check signatures match exactly
    import inspect
    groq_sig = inspect.signature(GroqAdapter.create)
    ollama_sig = inspect.signature(OllamaAdapter.create)
    assert_ok(groq_sig == ollama_sig, "Signatures for .create() do not match between adapters!")
    
    print(f"{PASS} All deliverables exist and signatures match identically")


# ---------------------------------------------------------------------------
# STEP 2 Edge Cases
# ---------------------------------------------------------------------------

def test_ec1_to_ec3_factory():
    print("\n--- EC1-EC3: Factory initialization ---")
    from app.agent.llm_client import get_llm_client, GroqAdapter, OllamaAdapter
    from app.config import settings
    
    # EC1: Groq
    with patch.object(settings, "LLM_PROVIDER", "groq"):
        with patch.object(settings, "GROQ_API_KEY", "test_groq_key"):
            with patch.object(settings, "LLM_MODEL", "test-model-1"):
                client = get_llm_client()
                assert_ok(isinstance(client, GroqAdapter), "Did not return GroqAdapter")
                assert_ok(client._model == "test-model-1", "Model config missing")
                # We can't trivially check the api key inside the mock groq client, but we checked the model.
                print(f"{PASS} EC1: get_llm_client('groq') configures GroqAdapter from settings")

    # EC2: Ollama
    with patch.object(settings, "LLM_PROVIDER", "ollama"):
        with patch.object(settings, "OLLAMA_BASE_URL", "http://test:11434"):
            with patch.object(settings, "LLM_MODEL", "test-model-2"):
                client = get_llm_client()
                assert_ok(isinstance(client, OllamaAdapter), "Did not return OllamaAdapter")
                assert_ok(client.base_url == "http://test:11434", "Base URL config missing")
                assert_ok(client.model == "test-model-2", "Model config missing")
                print(f"{PASS} EC2: get_llm_client('ollama') configures OllamaAdapter from settings")

    # EC3: Invalid
    with patch.object(settings, "LLM_PROVIDER", "something_invalid"):
        try:
            get_llm_client()
            assert_ok(False, "Should have raised ValueError")
        except ValueError as e:
            assert_ok("Unrecognized LLM_PROVIDER" in str(e), "Wrong error message")
            print(f"{PASS} EC3: Invalid provider raises ValueError immediately at call time")


def test_ec4_and_ec5_multi_property_schema():
    print("\n--- EC4 & EC5: Multi-property tool schema translation ---")
    from app.agent.llm_client import _translate_anthropic_tools_to_openai
    
    # Complex Anthropic-style tool schema
    anthropic_tools = [{
        "name": "generate_diagram",
        "description": "Renders a diagram.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The code"},
                "complexity": {"type": "integer", "default": 1},
                "style": {"type": "string", "enum": ["light", "dark"]}
            },
            "required": ["code"]
        }
    }]
    
    translated = _translate_anthropic_tools_to_openai(anthropic_tools)
    
    assert_ok(len(translated) == 1, "Length mismatch")
    t = translated[0]
    assert_ok(t["type"] == "function", "Missing type: function")
    func = t["function"]
    assert_ok(func["name"] == "generate_diagram", "Name mismatch")
    
    # Check inner shape
    params = func["parameters"]
    assert_ok(params["type"] == "object", "Parameters type missing")
    assert_ok("complexity" in params["properties"], "Properties missing")
    assert_ok(params["properties"]["complexity"]["type"] == "integer", "Property type mutated")
    assert_ok("code" in params["required"], "Required array mutated")
    
    print(f"{PASS} EC4 & EC5: Multi-property Anthropic schema flawlessly translated to OpenAI/Groq/Ollama shape")


def test_ec6_to_ec8_stop_reasons_and_multi_tool():
    print("\n--- EC6, EC7 & EC8: Stop reasons and Multi-tool block parsing ---")
    from app.agent.llm_client import GroqAdapter
    
    # We will test Groq's parser
    groq_adapter = GroqAdapter("key", "model")
    
    # Construct a mock Groq response with TWO tool calls
    mock_res = MagicMock()
    mock_res.choices[0].finish_reason = "tool_calls"
    mock_res.choices[0].message.content = None
    
    tc1 = MagicMock()
    tc1.type = "function"
    tc1.id = "call_123"
    tc1.function.name = "tool_a"
    tc1.function.arguments = '{"arg": 1}'
    
    tc2 = MagicMock()
    tc2.type = "function"
    tc2.id = "call_456"
    tc2.function.name = "tool_b"
    tc2.function.arguments = '{"arg": 2}'
    
    mock_res.choices[0].message.tool_calls = [tc1, tc2]
    mock_res.usage.prompt_tokens = 10
    mock_res.usage.completion_tokens = 20
    
    groq_adapter._client.chat.completions.create = MagicMock(return_value=mock_res)
    
    res = groq_adapter.create("sys", [{"role": "user", "content": "hello"}])
    
    # EC6
    assert_ok(res.stop_reason == "tool_use", f"Expected tool_use, got {res.stop_reason}")
    print(f"{PASS} EC6: tool_calls finish reason translates to 'tool_use'")
    
    # EC8
    assert_ok(len(res.content) == 2, f"Expected 2 tool blocks, got {len(res.content)}")
    assert_ok(res.content[0]["id"] == "call_123", "First block ID mismatch")
    assert_ok(res.content[0]["name"] == "tool_a", "First block name mismatch")
    assert_ok(res.content[0]["input"] == {"arg": 1}, "First block input parsed incorrectly")
    
    assert_ok(res.content[1]["id"] == "call_456", "Second block ID mismatch")
    assert_ok(res.content[1]["name"] == "tool_b", "Second block name mismatch")
    print(f"{PASS} EC8: Multi-tool requests produce perfectly distinct, correctly ordered tool_use blocks")
    
    # EC7
    mock_res.choices[0].finish_reason = "stop"
    mock_res.choices[0].message.tool_calls = None
    mock_res.choices[0].message.content = "Plain text"
    
    res2 = groq_adapter.create("sys", [{"role": "user", "content": "hello"}])
    assert_ok(res2.stop_reason == "end_turn", f"Expected end_turn, got {res2.stop_reason}")
    assert_ok(res2.content[0]["text"] == "Plain text", "Text block missing")
    print(f"{PASS} EC7: Plain text responses translate to 'end_turn'")


def test_ec9_groq_rate_limit():
    print("\n--- EC9: Groq Rate Limit Classification ---")
    from app.agent.llm_client import GroqAdapter, RateLimitError, ProviderError
    import groq
    
    adapter = GroqAdapter("key", "model")
    
    # Simulate a 429
    adapter._client.chat.completions.create.side_effect = groq.RateLimitError(
        message="Too many requests",
        response=MagicMock(),
        body={}
    )
    
    try:
        adapter.create("sys", [])
        assert_ok(False, "Should raise RateLimitError")
    except RateLimitError:
        print(f"{PASS} EC9: Groq 429 correctly classified as explicitly retryable RateLimitError")
        
    # Simulate a generic error
    adapter._client.chat.completions.create.side_effect = Exception("Unknown")
    try:
        adapter.create("sys", [])
        assert_ok(False, "Should raise ProviderError")
    except ProviderError:
        print(f"{PASS} EC9: Generic error correctly classified as non-retryable ProviderError")


def test_ec10_ollama_unreachable():
    print("\n--- EC10: Ollama unreachable error handling ---")
    from app.agent.llm_client import OllamaAdapter, ProviderError
    import httpx
    
    adapter = OllamaAdapter("http://localhost:9999", "model")
    
    adapter.client.post = MagicMock(side_effect=httpx.ConnectError("Connection refused"))
    
    try:
        adapter.create("sys", [])
        assert_ok(False, "Should raise ProviderError")
    except ProviderError as e:
        assert_ok("unreachable" in str(e).lower(), f"Error message missing 'unreachable' detail: {str(e)}")
        print(f"{PASS} EC10: Ollama ConnectError surfaces as clean 'unreachable' ProviderError")


def test_ec11_malformed_arguments():
    print("\n--- EC11: Malformed tool arguments ---")
    from app.agent.llm_client import GroqAdapter
    
    groq_adapter = GroqAdapter("key", "model")
    
    mock_res = MagicMock()
    mock_res.choices[0].finish_reason = "tool_calls"
    mock_res.choices[0].message.content = None
    
    tc1 = MagicMock()
    tc1.type = "function"
    tc1.id = "call_malformed"
    tc1.function.name = "tool_c"
    tc1.function.arguments = '{malformed: "json' # Invalid JSON!
    
    mock_res.choices[0].message.tool_calls = [tc1]
    groq_adapter._client.chat.completions.create = MagicMock(return_value=mock_res)
    
    res = groq_adapter.create("sys", [])
    
    assert_ok(res.content[0]["id"] == "call_malformed", "ID missing")
    assert_ok(res.content[0]["input"] == '{malformed: "json', "Did not pass raw malformed string as fallback")
    print(f"{PASS} EC11: Malformed JSON arguments are passed through honestly as strings for Module 9 to handle")


# ---------------------------------------------------------------------------
# STEP 3: Boundary - No provider imports elsewhere
# ---------------------------------------------------------------------------
def test_step3_provider_boundaries():
    print("\n--- STEP 3: Verification of 'only file that knows wire formats' ---")
    
    skip_dirs = {
        ".venv", "venv", "venv312", "node_modules", "__pycache__",
        ".git", "repos", "data", "chroma_db", "bm25_index", "graph_store",
    }
    violations = []
    for fpath in PROJECT_ROOT.rglob("*.py"):
        if any(part in skip_dirs for part in fpath.parts):
            continue
        if ".gemini" in str(fpath):
            continue
        # Ignore this test file itself, ignore llm_client.py
        if fpath.name in ("test_module_8.py", "llm_client.py"):
            continue
            
        code = fpath.read_text(encoding="utf-8")
        if "import groq" in code or "from groq" in code:
            violations.append(f"{fpath.name} imports groq")
            
        # Hard to perfectly grep for all ollama raw calls, but we can look for hitting `/api/chat` via httpx directly
        if "httpx.post" in code and "/api/chat" in code:
            violations.append(f"{fpath.name} hits Ollama API directly")
            
    assert_ok(len(violations) == 0, f"Provider boundaries violated! {violations}")
    print(f"{PASS} Zero provider-specific SDK imports or raw API calls found outside llm_client.py")


# ---------------------------------------------------------------------------
# STEP 4: Handoff Verification
# ---------------------------------------------------------------------------
def test_step4_handoff():
    print("\n--- STEP 4: Round-trip handoff verification ---")
    # We already tested this in EC8, but let's confirm the expected consumption pattern exactly.
    from app.agent.llm_client import GroqAdapter
    groq_adapter = GroqAdapter("key", "model")
    
    mock_res = MagicMock()
    mock_res.choices[0].finish_reason = "tool_calls"
    mock_res.choices[0].message.content = None
    tc1 = MagicMock()
    tc1.type = "function"
    tc1.id = "call_123"
    tc1.function.name = "test_tool"
    tc1.function.arguments = '{"a": 1}'
    mock_res.choices[0].message.tool_calls = [tc1]
    
    groq_adapter._client.chat.completions.create = MagicMock(return_value=mock_res)
    
    res = groq_adapter.create("sys", [])
    
    # The consumption pattern:
    blocks = res.content
    tool_blocks = [b for b in blocks if b["type"] == "tool_use"]
    
    assert_ok(len(tool_blocks) == 1, "Tool block extraction failed")
    assert_ok("id" in tool_blocks[0], "Missing ID")
    assert_ok("name" in tool_blocks[0], "Missing Name")
    assert_ok("input" in tool_blocks[0], "Missing Input")
    assert_ok(isinstance(tool_blocks[0]["input"], dict), "Input isn't a dict")
    
    print(f"{PASS} Full round-trip handoff strictly conforms to the expected structural pattern for Module 9")


# ---------------------------------------------------------------------------
# STEP 5: Static / Boundary Checks
# ---------------------------------------------------------------------------
def test_step5_static_checks():
    print("\n--- STEP 5: Static Boundary Checks ---")
    llm_path = PROJECT_ROOT / "app/agent/llm_client.py"
    code = llm_path.read_text(encoding="utf-8")
    
    assert_ok("TOOL_DEFINITIONS" not in code, "TOOL_DEFINITIONS hardcoded in llm_client!")
    assert_ok("You are Antigravity" not in code, "System prompt leaked into llm_client!")
    
    # Parser loops are allowed; retry orchestration (while True / stamina) is not.
    import ast
    tree = ast.parse(code)
    retry_whiles = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.While)
        and isinstance(getattr(n.test, "value", None), bool)
        and n.test.value is True
    ]
    assert_ok(not retry_whiles, "Retry orchestration loop (while True) found in llm_client!")
    assert_ok("stamina" not in code, "Stamina retry package imported in llm_client!")
    
    print(f"{PASS} Zero system prompts, zero tool schemas, and zero retry orchestration found")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 8 Tests: LLM Provider Abstraction")
    print("=" * 60)

    test_step1_deliverables()
    test_ec1_to_ec3_factory()
    test_ec4_and_ec5_multi_property_schema()
    test_ec6_to_ec8_stop_reasons_and_multi_tool()
    test_ec9_groq_rate_limit()
    test_ec10_ollama_unreachable()
    test_ec11_malformed_arguments()
    test_step3_provider_boundaries()
    test_step4_handoff()
    test_step5_static_checks()

    print("\n" + "=" * 60)
    print("=== Module 8: TESTS COMPLETED ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
