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


def plan_prompt(question: str, memory: dict[str, Any] | None = None) -> str:
    """
    Build the PLAN-state user prompt.

    Included: question, iteration count, brief prior-plan hint (if any).
    Excluded: full tool-result history, assembled retrieval context, chat transcript.
    """
    mem = memory or {}
    iteration = int(mem.get("iteration", 0))
    prior_tool = mem.get("last_tool_name")
    repo_id = mem.get("repo_id", "")

    example = {
        "tool_name": "search_code",
        "arguments": {"query": "authentication flow", "top_k": 5},
    }

    lines = [
        "You are the PLAN step of a codebase onboarding agent.",
        "Choose exactly ONE tool call to gather evidence for the user question.",
        "",
        _JSON_ONLY_INSTRUCTION,
        "",
        "Required JSON shape:",
        json.dumps(example, indent=2),
        "",
        f"Allowed tool_name values: {', '.join(_ALLOWED_TOOLS)}.",
        "arguments must match that tool's schema (strings and integers only).",
        "",
        f"Repository: {repo_id or 'unknown'}",
        f"Planning iteration: {iteration}",
    ]

    if prior_tool:
        lines.append(f"Previous tool used: {prior_tool} (pick a different tool if more context is needed).")

    lines.extend([
        "",
        "Keep arguments concise. Prefer top_k between 3 and 8 for search_code.",
        "",
        "USER QUESTION:",
        question.strip(),
    ])

    return "\n".join(lines)
