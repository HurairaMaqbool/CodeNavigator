"""
tests/test_llm.py
-----------------
Unit tests for Module 8 (LLM Provider Abstraction).

Run with:
    python -m unittest tests/test_llm.py -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Bootstrap: mock structlog
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

from app.config import settings
from app.agent.llm_client import (
    GroqAdapter,
    OllamaAdapter,
    ProviderError,
    RateLimitError,
    _translate_anthropic_tools_to_openai,
    get_llm_client,
)

class TestToolTranslation(unittest.TestCase):
    def test_anthropic_to_openai_schema(self):
        anthropic_tools = [
            {
                "name": "search_code",
                "description": "Search the codebase",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        ]

        openai_tools = _translate_anthropic_tools_to_openai(anthropic_tools)
        self.assertEqual(len(openai_tools), 1)
        t = openai_tools[0]
        self.assertEqual(t["type"], "function")
        self.assertEqual(t["function"]["name"], "search_code")
        self.assertEqual(t["function"]["description"], "Search the codebase")
        self.assertIn("query", t["function"]["parameters"]["properties"])
        self.assertIn("query", t["function"]["parameters"]["required"])

class TestFactory(unittest.TestCase):
    def test_factory_invalid_provider(self):
        old = settings.LLM_PROVIDER
        settings.LLM_PROVIDER = "unknown_provider"
        try:
            with self.assertRaisesRegex(ValueError, "Unrecognized LLM_PROVIDER"):
                get_llm_client()
        finally:
            settings.LLM_PROVIDER = old

class TestGroqAdapter(unittest.TestCase):
    @patch("groq.Groq")
    def test_groq_normalization_text(self, mock_groq_class):
        # Setup mock
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_res = MagicMock()
        mock_choice = MagicMock()
        mock_msg = MagicMock()
        
        mock_msg.content = "Here is my answer."
        mock_msg.tool_calls = None
        mock_choice.message = mock_msg
        mock_choice.finish_reason = "stop"
        mock_res.choices = [mock_choice]
        mock_res.usage.prompt_tokens = 10
        mock_res.usage.completion_tokens = 20
        mock_client.chat.completions.create.return_value = mock_res
        
        adapter = GroqAdapter("api_key", "model")
        res = adapter.create("system", [{"role": "user", "content": "hi"}])
        
        self.assertEqual(res.stop_reason, "end_turn")
        self.assertEqual(len(res.content), 1)
        self.assertEqual(res.content[0]["type"], "text")
        self.assertEqual(res.content[0]["text"], "Here is my answer.")
        self.assertEqual(res.usage["input_tokens"], 10)

    @patch("groq.Groq")
    def test_groq_normalization_tools(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_res = MagicMock()
        mock_choice = MagicMock()
        mock_msg = MagicMock()
        
        mock_msg.content = "Let me check that."
        
        mock_tc1 = MagicMock()
        mock_tc1.id = "call_1"
        mock_tc1.type = "function"
        mock_tc1.function.name = "search_code"
        mock_tc1.function.arguments = '{"query": "test"}'
        
        mock_msg.tool_calls = [mock_tc1]
        mock_choice.message = mock_msg
        mock_choice.finish_reason = "tool_calls"
        mock_res.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_res
        
        adapter = GroqAdapter("api_key", "model")
        res = adapter.create("system", [{"role": "user", "content": "hi"}])
        
        self.assertEqual(res.stop_reason, "tool_use")
        self.assertEqual(len(res.content), 2)
        self.assertEqual(res.content[0]["type"], "text")
        
        tool_block = res.content[1]
        self.assertEqual(tool_block["type"], "tool_use")
        self.assertEqual(tool_block["id"], "call_1")
        self.assertEqual(tool_block["name"], "search_code")
        self.assertEqual(tool_block["input"]["query"], "test")


    @patch("groq.Groq")
    def test_groq_coerces_text_function_tags(self, mock_groq_class):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_res = MagicMock()
        mock_choice = MagicMock()
        mock_msg = MagicMock()

        mock_msg.content = (
            'I will search the codebase.\n'
            '<function=search_code>{"query": "Session vs get", "top_k": 3}</function>'
        )
        mock_msg.tool_calls = None
        mock_choice.message = mock_msg
        mock_choice.finish_reason = "stop"
        mock_res.choices = [mock_choice]
        mock_res.usage = MagicMock(prompt_tokens=5, completion_tokens=10)
        mock_client.chat.completions.create.return_value = mock_res

        adapter = GroqAdapter("api_key", "model")
        res = adapter.create("system", [{"role": "user", "content": "hi"}])

        self.assertEqual(res.stop_reason, "tool_use")
        tool_blocks = [b for b in res.content if b["type"] == "tool_use"]
        self.assertEqual(len(tool_blocks), 1)
        self.assertEqual(tool_blocks[0]["name"], "search_code")
        self.assertEqual(tool_blocks[0]["input"]["query"], "Session vs get")


class TestOllamaAdapter(unittest.TestCase):
    @patch("httpx.Client.post")
    def test_ollama_unreachable(self, mock_post):
        import httpx
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        
        adapter = OllamaAdapter("http://localhost:11434", "qwen2.5:14b")
        with self.assertRaisesRegex(ProviderError, "Ollama server unreachable"):
            adapter.create("sys", [{"role": "user", "content": "hello"}])
            
    @patch("httpx.Client.post")
    def test_ollama_normalization_tools(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "model": "qwen",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_callers",
                            "arguments": {"name": "foo"}
                        }
                    }
                ]
            },
            "done_reason": "stop"
        }
        mock_post.return_value = mock_response
        
        adapter = OllamaAdapter("http://localhost:11434", "qwen")
        res = adapter.create("sys", [])
        
        self.assertEqual(res.stop_reason, "tool_use")
        self.assertEqual(len(res.content), 1)
        self.assertEqual(res.content[0]["type"], "tool_use")
        self.assertEqual(res.content[0]["name"], "get_callers")
        self.assertEqual(res.content[0]["input"]["name"], "foo")
        self.assertIn("id", res.content[0]) # Generated UUID since Ollama didn't provide it

if __name__ == "__main__":
    unittest.main(verbosity=2)
