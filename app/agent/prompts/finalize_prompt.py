# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/finalize_prompt.py
------------------------------------
FINALIZE state prompt — Layer 1 few-shot grounded examples + JSON contract.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.agent.prompts.answer_quality_dataset import (
    classify_query,
    dataset_available,
    finalize_system_quality_prompt,
    render_few_shot_section,
    render_negative_examples_section,
    render_pre_answer_checklist,
)

from app.agent.prompts.loader import load_private_prompt

_FALLBACK_JSON_SCHEMA = """\
RESPOND WITH JSON ONLY — no markdown fences, no prose outside the JSON object.

Schema:
{{
  "claims": [
    {{
      "claim": "<one atomic factual sentence>",
      "citation": {{
        "file_path": "<exact path from context>",
        "start_line": <int>,
        "end_line": <int>
      }}
    }}
  ]
}}

Rules for citations:
- Every factual claim MUST have a citation object with real line numbers from context.
- Use citation: null ONLY for honest abstention claims (what you found vs. could not confirm).
- One claim = one fact. Do not bundle multiple facts into one claim.
- Return at most {max_claims} claims total — prefer fewer, complete claims over many truncated ones.
"""

_FALLBACK_HARD_CONSTRAINTS = """\
HARD CONSTRAINTS (violations will be rejected):
1. Use ONLY the provided code context — never general Python/library background knowledge.
2. Every factual claim must have citation with real file_path and line numbers from context.
3. NEVER cite tests/ or test_*.py files for implementation behavior — use src/ only.
4. Cite the smallest method-level line range from the chunk manifest (not whole-class spans).
5. Each claim must add NEW information — do not repeat the same fact in different words.
6. If context does not fully answer the question, prefer grounded claims for what IS present.
   Add at most ONE abstention claim (citation: null) only for a specific sub-part that is truly absent.
7. Do NOT invent paths, line numbers, or behaviors not supported by the context.
"""

_FALLBACK_WHY_MODE = """\
WHY-QUESTION MODE:
- Lead with README/HISTORY or class docstring rationale when present in context.
- Explain design rationale (maintainability, reuse, complexity) — not only mechanism.
- Pair one doc/design claim with one implementation claim.
- If explicit 'why' is undocumented, prefix one claim with 'Inferred from structure:'.
"""

_JSON_SCHEMA = load_private_prompt("finalize_schema.txt", _FALLBACK_JSON_SCHEMA)
_HARD_CONSTRAINTS = load_private_prompt("finalize_constraints.txt", _FALLBACK_HARD_CONSTRAINTS)
_WHY_MODE = load_private_prompt("finalize_why_mode.txt", _FALLBACK_WHY_MODE)

# Compact legacy fallbacks when the JSON dataset is unavailable.
_LEGACY_FEW_SHOT_GOOD = """\
EXAMPLE — GOOD:
Question: How does Session.send prepare the outgoing request?
{"claims":[{"claim":"Session.send merges environment settings before dispatch.","citation":{"file_path":"src/requests/sessions.py","start_line":573,"end_line":585}}]}
"""

_LEGACY_FEW_SHOT_ABSTAIN = """\
EXAMPLE — GOOD ABSTENTION:
Question: How does requests configure urllib3 retry backoff?
{"claims":[{"claim":"Indexed context does not include urllib3 Retry/backoff configuration — cannot confirm from available chunks.","citation":null}]}
"""

_LEGACY_FEW_SHOT_BAD = """\
EXAMPLE — BAD: generic library overview with decorative README citation — DO NOT DO THIS.
"""


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _context_char_budget(*, instruction_text: str, question: str) -> int:
    """Reserve token budget for retrieval context after fixed FINALIZE instructions."""
    max_input = int(settings.GROQ_FINALIZE_MAX_INPUT_TOKENS)
    ctx_cap = int(settings.FINALIZE_CONTEXT_MAX_TOKENS)
    overhead = _estimate_tokens(instruction_text) + _estimate_tokens(question) + 32
    remaining_tokens = max(400, min(ctx_cap, max_input - overhead))
    return remaining_tokens * 4


def finalize_prompt(memory: dict[str, Any]) -> str:
    """
    Build the FINALIZE-state user prompt with few-shot grounded examples.

    Output contract: JSON list of {claim, citation} objects (Layer 2).
    """
    question = str(memory.get("question", "")).strip()
    raw_context = str(memory.get("assembled_context", ""))
    graph_context = str(memory.get("graph_context", "")).strip()
    is_why = bool(memory.get("is_why_query"))
    query_category = str(memory.get("query_category") or classify_query(question))
    use_dataset = dataset_available()

    lines = [
        "You are the FINALIZE step of a codebase onboarding agent.",
        "Produce structured grounded claims — NOT free-form markdown.",
        "",
        _JSON_SCHEMA.format(max_claims=int(settings.FINALIZE_MAX_CLAIMS)),
        "",
        _HARD_CONSTRAINTS,
    ]

    checklist = render_pre_answer_checklist(compact=True)
    if checklist:
        lines.extend(["", checklist])

    few_shot_block = render_few_shot_section(
        question,
        query_category,
        max_examples=1,
    )
    if few_shot_block:
        lines.extend(["", "FEW-SHOT GUIDANCE:", few_shot_block])

    neg_block = render_negative_examples_section(max_items=3)
    if neg_block:
        lines.extend(["", neg_block])

    if is_why or query_category == "REASONING":
        lines.extend(["", _WHY_MODE])

    if not use_dataset:
        lines.extend([
            "",
            _LEGACY_FEW_SHOT_GOOD,
            "",
            _LEGACY_FEW_SHOT_ABSTAIN,
            "",
            _LEGACY_FEW_SHOT_BAD,
        ])

    instruction_text = "\n".join(lines)
    context_chars = _context_char_budget(
        instruction_text=instruction_text,
        question=question,
    )
    context = raw_context[:context_chars]
    if len(raw_context) > len(context):
        context = context.rstrip() + "\n...[context truncated for token budget]"

    lines.extend([
        "",
        "USER QUESTION:",
        question,
        "",
        "RETRIEVAL CONTEXT:",
        context or "(no retrieval context)",
    ])

    if graph_context:
        graph_cap = min(800, max(200, context_chars // 8))
        lines.extend(["", "GRAPH CONTEXT:", graph_context[:graph_cap]])

    lines.extend(["", "Return the JSON object now."])
    return "\n".join(lines)


def finalize_system_prompt(question: str = "") -> str:
    """System line for FINALIZE — JSON claims only + answer-quality protocol."""
    if question.strip():
        return finalize_system_quality_prompt(question)
    return (
        "You are a codebase onboarding assistant. "
        "Respond with a single JSON object matching the claims schema. "
        "Use ONLY provided context. Never add general programming knowledge. "
        "Abstain honestly when context is insufficient. "
        "Never output chain-of-thought steps — only structured claims JSON."
    )


def estimate_finalize_input_tokens(question: str, assembled_context: str = "", **memory: Any) -> int:
    """Estimate total FINALIZE input tokens (system + user) for budget tests."""
    mem = {
        "question": question,
        "assembled_context": assembled_context,
        **memory,
    }
    system = finalize_system_prompt(question)
    user = finalize_prompt(mem)
    return _estimate_tokens(system) + _estimate_tokens(user)
