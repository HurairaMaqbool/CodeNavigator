# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/finalize_prompt.py
------------------------------------
FINALIZE state prompt — Layer 1 few-shot grounded examples + JSON contract.
"""
from __future__ import annotations

from typing import Any

_JSON_SCHEMA = """\
RESPOND WITH JSON ONLY — no markdown fences, no prose outside the JSON object.

Schema:
{
  "claims": [
    {
      "claim": "<one atomic factual sentence>",
      "citation": {
        "file_path": "<exact path from context>",
        "start_line": <int>,
        "end_line": <int>
      }
    }
  ]
}

Rules for citations:
- Every factual claim MUST have a citation object with real line numbers from context.
- Use citation: null ONLY for honest abstention claims (what you found vs. could not confirm).
- One claim = one fact. Do not bundle multiple facts into one claim.
"""

_HARD_CONSTRAINTS = """\
HARD CONSTRAINTS (violations will be rejected):
1. Use ONLY the provided code context — never general Python/library background knowledge.
2. Every factual claim must have citation with real file_path and line numbers from context.
3. If context does not fully answer the question, add an abstention claim (citation: null)
   stating what you found and what you could NOT confirm from the available code.
4. Do NOT invent paths, line numbers, or behaviors not supported by the context.
"""

_FEW_SHOT_GOOD = """\
EXAMPLE — GOOD (grounded, inline-ready citations):
Question: How does Session.send prepare the outgoing request?
{
  "claims": [
    {
      "claim": "Session.send merges environment settings into the request via merge_environment_settings before dispatch.",
      "citation": {"file_path": "src/requests/sessions.py", "start_line": 573, "end_line": 585}
    },
    {
      "claim": "The method obtains a Request object and passes it to self.request for the actual HTTP exchange.",
      "citation": {"file_path": "src/requests/sessions.py", "start_line": 586, "end_line": 598}
    }
  ]
}
"""

_FEW_SHOT_ABSTAIN = """\
EXAMPLE — GOOD ABSTENTION (honest partial answer, no filler):
Question: How does requests configure urllib3 retry backoff for connection errors?
{
  "claims": [
    {
      "claim": "The indexed context shows Session and HTTPAdapter in sessions.py but does not include urllib3 Retry/backoff configuration — I cannot confirm retry backoff behavior from the available chunks.",
      "citation": null
    }
  ]
}
"""

_FEW_SHOT_BAD = """\
EXAMPLE — BAD (DO NOT DO THIS — generic training knowledge, weak citation):
{
  "claims": [
    {
      "claim": "Requests is a popular HTTP library for Python that simplifies making API calls with sessions and cookies.",
      "citation": {"file_path": "README.md", "start_line": 1, "end_line": 10}
    }
  ]
}
Why bad: generic library overview not tied to specific mechanism in context; citation is decorative.
"""


def finalize_prompt(memory: dict[str, Any]) -> str:
    """
    Build the FINALIZE-state user prompt with few-shot grounded examples.

    Output contract: JSON list of {claim, citation} objects (Layer 2).
    """
    question = str(memory.get("question", "")).strip()
    context = str(memory.get("assembled_context", ""))[:12000]
    graph_context = str(memory.get("graph_context", "")).strip()

    lines = [
        "You are the FINALIZE step of a codebase onboarding agent.",
        "Produce structured grounded claims — NOT free-form markdown.",
        "",
        _JSON_SCHEMA,
        "",
        _HARD_CONSTRAINTS,
        "",
        _FEW_SHOT_GOOD,
        "",
        _FEW_SHOT_ABSTAIN,
        "",
        _FEW_SHOT_BAD,
        "",
        "USER QUESTION:",
        question,
        "",
        "RETRIEVAL CONTEXT:",
        context or "(no retrieval context)",
    ]

    if graph_context:
        lines.extend(["", "GRAPH CONTEXT:", graph_context[:2000]])

    lines.extend(["", "Return the JSON object now."])
    return "\n".join(lines)


def finalize_system_prompt() -> str:
    """System line for FINALIZE — JSON claims only."""
    return (
        "You are a codebase onboarding assistant. "
        "Respond with a single JSON object matching the claims schema. "
        "Use ONLY provided context. Never add general programming knowledge. "
        "Abstain honestly when context is insufficient."
    )
