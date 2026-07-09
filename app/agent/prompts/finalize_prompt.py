# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/finalize_prompt.py
------------------------------------
FINALIZE state prompt — pure string builder, zero LLM/network calls.
"""
from __future__ import annotations

from typing import Any

_CITATION_INSTRUCTION = (
    "Cite EVERY factual claim using backticks with the exact format "
    "`file_path:start_line-end_line` (example: `src/auth/login.py:42-58`). "
    "Use a single line number as `file_path:12` when the claim refers to one line. "
    "Do not invent paths or line numbers not supported by the context."
)


def finalize_prompt(memory: dict[str, Any]) -> str:
    """
    Build the FINALIZE-state user prompt.

    Included: user question, assembled retrieval/graph context for answering.
    Excluded: planning metadata, decide JSON, chat transcript, compress summaries.
    """
    question = str(memory.get("question", "")).strip()
    context = str(memory.get("assembled_context", ""))[:12000]
    graph_context = str(memory.get("graph_context", "")).strip()

    lines = [
        "You are the FINALIZE step of a codebase onboarding agent.",
        "Write a concise markdown answer using ONLY the context below.",
        "",
        _CITATION_INSTRUCTION,
        "",
        "If the context is insufficient, state what is missing — do not guess file paths.",
        "Target length: 150-400 words unless the question is trivial.",
        "",
        "USER QUESTION:",
        question,
        "",
        "RETRIEVAL CONTEXT:",
        context or "(no retrieval context)",
    ]

    if graph_context:
        lines.extend(["", "GRAPH CONTEXT:", graph_context[:2000]])

    lines.append("")
    lines.append("Provide the final markdown answer now.")

    return "\n".join(lines)


def finalize_system_prompt() -> str:
    """Optional system line for FINALIZE Groq calls (markdown + citations only)."""
    return (
        "You are a codebase onboarding assistant. Output markdown only. "
        + _CITATION_INSTRUCTION
    )
