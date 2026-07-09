"""Module #23 — state-specific prompt builders."""
from __future__ import annotations

import pytest

from app.agent.prompts import (
    compress_prompt,
    decide_prompt,
    finalize_prompt,
    finalize_system_prompt,
    plan_prompt,
)


def test_plan_prompt_returns_string_with_json_only_instruction():
    out = plan_prompt("How does login work?", {"iteration": 0, "repo_id": "r1"})
    assert isinstance(out, str)
    assert "RESPOND WITH JSON ONLY" in out
    assert "tool_name" in out
    assert "arguments" in out
    assert "How does login work?" in out
    assert "search_code" in out


def test_plan_prompt_excludes_tool_history():
    out = plan_prompt("Q?", {"iteration": 1, "last_tool_name": "read_file"})
    assert "USER QUESTION" in out
    assert "assembled" not in out.lower()
    assert "Previous tool used: read_file" in out


def test_decide_prompt_json_shape_instruction():
    out = decide_prompt({
        "question": "What calls main?",
        "assembled_context": "def main(): pass",
        "iteration": 1,
        "chunk_count": 3,
        "max_iterations": 3,
    })
    assert "RESPOND WITH JSON ONLY" in out
    assert "needs_more" in out
    assert "reason" in out
    assert "What calls main?" in out
    assert "def main(): pass" in out


def test_finalize_prompt_citation_format_instruction():
    out = finalize_prompt({
        "question": "Explain auth",
        "assembled_context": "### auth.py\ndef login(): pass",
    })
    assert "`file_path:start_line-end_line`" in out
    assert "src/auth/login.py:42-58" in out
    assert "Explain auth" in out
    assert "RESPOND WITH JSON ONLY" not in out


def test_finalize_system_prompt_citations():
    sys = finalize_system_prompt()
    assert "file_path:start_line-end_line" in sys


def test_compress_prompt_includes_old_results_only():
    old = [{"tool": "search_code", "results": [{"file_path": "a.py"}]}]
    out = compress_prompt(old)
    assert "Tool Output 1" in out
    assert "a.py" in out
    assert "USER QUESTION" not in out


def test_compress_prompt_accepts_strings():
    out = compress_prompt(["raw output text"])
    assert "raw output text" in out


def test_prompts_never_raise_on_empty_memory():
    assert plan_prompt("q", {})
    assert decide_prompt({"question": "q", "assembled_context": ""})
    assert finalize_prompt({"question": "q", "assembled_context": ""})
    assert compress_prompt([])


def test_plan_prompt_embeds_parseable_example():
    out = plan_prompt("test", {})
    assert '"tool_name": "search_code"' in out
    assert '"query": "authentication flow"' in out
    assert '"top_k": 5' in out
