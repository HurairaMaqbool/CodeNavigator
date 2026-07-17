# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/plan_prompt.py
--------------------------------
PLAN state prompt — pure string builder, zero LLM/network calls.
"""
from __future__ import annotations

import json
from typing import Any

_ALLOWED_TOOLS = (
    "search_code",
    "read_file",
    "get_callers",
    "get_callees",
    "generate_diagram",
)

_JSON_ONLY_INSTRUCTION = (
    "RESPOND WITH JSON ONLY. No markdown fences, no explanation, no prose before or after. "
    "Your entire response must be exactly one JSON object."
)


from app.agent.prompts.loader import load_private_prompt

_FALLBACK_PLAN_PROMPT = """You are the PLAN step of a codebase onboarding agent.
Choose exactly ONE tool call to gather evidence for the user question.

RESPOND WITH JSON ONLY. No markdown fences, no explanation, no prose before or after.
Your entire response must be exactly one JSON object.

Required JSON shape:
{{
  "tool_name": "search_code",
  "arguments": {{
    "query": "authentication flow",
    "top_k": 5
  }}
}}

Allowed tool_name values: search_code, read_file, get_callers, get_callees, generate_diagram.
arguments must match that tool's schema (strings and integers only).

Repository: {repo_id}
Planning iteration: {iteration}
{prior_tool_line}

Keep arguments concise. Prefer top_k between 3 and 8 for search_code.

USER QUESTION:
{question}"""


def plan_prompt(question: str, memory: dict[str, Any] | None = None) -> str:
    """
    Build the PLAN-state user prompt.
    """
    mem = memory or {}
    iteration = int(mem.get("iteration", 0))
    prior_tool = mem.get("last_tool_name")
    repo_id = mem.get("repo_id", "")

    prior_tool_line = ""
    if prior_tool:
        prior_tool_line = f"Previous tool used: {prior_tool} (pick a different tool if more context is needed)."

    template = load_private_prompt("plan_prompt.txt", _FALLBACK_PLAN_PROMPT)
    return template.format(
        repo_id=repo_id or "unknown",
        iteration=iteration,
        prior_tool_line=prior_tool_line,
        question=question.strip(),
    )
