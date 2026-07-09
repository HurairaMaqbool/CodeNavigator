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


def decide_prompt(memory: dict[str, Any]) -> str:
    """
    Build the DECIDE-state user prompt.

    Included: question, assembled retrieval context snippet, iteration, chunk count.
    Excluded: raw chat history, uncompressed tool JSON blobs, finalize-only instructions.
    """
    question = str(memory.get("question", "")).strip()
    context = str(memory.get("assembled_context", ""))[:3000]
    iteration = int(memory.get("iteration", 0))
    chunk_count = int(memory.get("chunk_count", 0))
    max_iterations = int(memory.get("max_iterations", 3))

    example_yes = {"needs_more": False, "reason": "Context covers the asked behavior."}
    example_no = {"needs_more": True, "reason": "Missing implementation details for the cited module."}

    return "\n".join([
        "You are the DECIDE step of a codebase onboarding agent.",
        "Decide whether the retrieved context is sufficient to answer accurately,",
        "or whether another retrieval pass is required.",
        "",
        _JSON_ONLY_INSTRUCTION,
        "",
        "Required JSON shape (boolean field must be needs_more, string field must be reason):",
        f"If sufficient: {json.dumps(example_yes)}",
        f"If insufficient: {json.dumps(example_no)}",
        "",
        f"Iteration: {iteration} of {max_iterations}",
        f"Retrieved chunks in context: {chunk_count}",
        "",
        "USER QUESTION:",
        question,
        "",
        "ASSEMBLED CONTEXT (truncated):",
        context or "(empty)",
    ])
