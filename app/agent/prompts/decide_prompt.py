# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/decide_prompt.py
----------------------------------
DECIDE state prompt — pure string builder, zero LLM/network calls.
"""
from __future__ import annotations

import json
from typing import Any

_JSON_ONLY_INSTRUCTION = (
    "RESPOND WITH JSON ONLY. No markdown fences, no explanation, no prose before or after. "
    "Your entire response must be exactly one JSON object."
)


from app.agent.prompts.loader import load_private_prompt

_FALLBACK_DECIDE_PROMPT = """You are the DECIDE step of a codebase onboarding agent.
Decide whether the retrieved context is sufficient to answer accurately,
or whether another retrieval pass is required.

RESPOND WITH JSON ONLY. No markdown fences, no explanation, no prose before or after.
Your entire response must be exactly one JSON object.

Required JSON shape (boolean field must be needs_more, string field must be reason):
If sufficient: {{"needs_more": false, "reason": "Context covers the asked behavior."}}
If insufficient: {{"needs_more": true, "reason": "Missing implementation details for the cited module."}}

Iteration: {iteration} of {max_iterations}
Retrieved chunks in context: {chunk_count}

USER QUESTION:
{question}

ASSEMBLED CONTEXT (truncated):
{context}"""


def decide_prompt(memory: dict[str, Any]) -> str:
    """
    Build the DECIDE-state user prompt.
    """
    question = str(memory.get("question", "")).strip()
    context = str(memory.get("assembled_context", ""))[:3000]
    iteration = int(memory.get("iteration", 0))
    chunk_count = int(memory.get("chunk_count", 0))
    max_iterations = int(memory.get("max_iterations", 3))

    template = load_private_prompt("decide_prompt.txt", _FALLBACK_DECIDE_PROMPT)
    return template.format(
        iteration=iteration,
        max_iterations=max_iterations,
        chunk_count=chunk_count,
        question=question,
        context=context or "(empty)",
    )
