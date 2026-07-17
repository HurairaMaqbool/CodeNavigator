# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/system_prompt.py
--------------------------
Canonical system prompt for the code QA agent loop.
"""

from app.agent.prompts.loader import load_private_prompt

_FALLBACK_SYSTEM_PROMPT = """You are a codebase analyst assistant. Answer user queries strictly using the provided codebase search results. Cite files using path:line format."""
SYSTEM_PROMPT = load_private_prompt("system_prompt.txt", _FALLBACK_SYSTEM_PROMPT)

# Appended dynamically by the agent loop — never shown to users.
DIRECTIVE_FORCE_SEARCH = (
    "\n\n[DIRECTIVE] You have not used any tools yet. Call search_code with a specific "
    "symbol or keyword before answering. Do not reply with text only."
)

DIRECTIVE_BUDGET_EXHAUSTED = (
    "\n\n[DIRECTIVE] Search budget reached. Produce your final answer now using context "
    "already in this conversation. Cite file paths and line numbers. Do not mention tools."
)

DIRECTIVE_TOOL_FORMAT_ERROR = (
    "\n\n[DIRECTIVE] Your last tool call was malformed. Use the native tool-calling API only. "
    "Do not emit <function> tags or raw JSON in your reply."
)

# Bump when SYSTEM_PROMPT changes materially — semantic cache invalidates on mismatch.
PROMPT_VERSION = "2026-06-27-v3"
