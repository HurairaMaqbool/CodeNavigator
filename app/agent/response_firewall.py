"""
app/agent/response_firewall.py
------------------------------
Final sanitization layer for all user-visible agent text.

The LLM is not trusted to format answers correctly. Every string shown in the
chat UI or API `answer` field must pass through ``sanitize_user_answer`` so
tool syntax, internal loop notices, and meta-commentary never leak — even if
the model ignores the system prompt or Groq emits malformed tool calls.
"""
from __future__ import annotations

import re

# Groq/Llama text-tool leaks
_FUNCTION_TAG = re.compile(
    r"<function=[a-zA-Z0-9_-]+>\s*\{.*?\}\s*(?:</function>)?",
    re.DOTALL,
)

# Internal loop / budget / retry phrases the model sometimes echoes
_INTERNAL_PHRASES = re.compile(
    r"(?:"
    r"tool call budget exhausted|"
    r"budget exhausted|"
    r"you (?:did not|must) use (?:any )?tools?|"
    r"please call a tool|"
    r"i will (?:try|use|search)|"
    r"let me (?:try|search|check|use)|"
    r"i(?:'ll| will) (?:search|try|use) (?:a |the )?(?:different )?(?:query|search|tool)|"
    r"you can use (?:the )?read_file|"
    r"system note:|"
    r"notice:\s*you"
    r")",
    re.IGNORECASE,
)

# Trailing recap / filler the model adds despite instructions
_FILLER_START = re.compile(
    r"^\s*(?:In summary|Overall|Therefore|It's worth noting|In addition|"
    r"To summarize|In conclusion|Additionally)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Strip lines that are purely meta (agent thought/action scaffolding)
_META_LINE = re.compile(
    r"^\s*(?:agent\s+(?:thought|action|observation)|"
    r"(?:i\s+)?(?:will|need to)\s+(?:search|try|use)|"
    r"this should give me)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)

# Trailing "search_code(...)" style mentions
_TOOL_NAME_LEAK = re.compile(
    r"\b(?:search_code|read_file|get_callers|get_callees|get_subgraph|search_web_docs)"
    r"\s*\([^)]*\)",
    re.IGNORECASE,
)


def sanitize_user_answer(text: str) -> str:
    """
    Return text safe to show end users. Idempotent.
    """
    if not text:
        return ""

    out = text
    out = _FUNCTION_TAG.sub("", out)
    out = _TOOL_NAME_LEAK.sub("", out)
    out = _META_LINE.sub("", out)

    # Remove sentences containing internal phrases
    sentences = re.split(r"(?<=[.!?])\s+", out)
    cleaned: list[str] = []
    for sent in sentences:
        if _INTERNAL_PHRASES.search(sent):
            continue
        if _FILLER_START.match(sent):
            continue
        cleaned.append(sent)
    out = " ".join(cleaned)

    # Collapse whitespace
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def has_forbidden_leak(text: str) -> bool:
    """True if text still contains patterns that must never reach users."""
    if not text:
        return False
    if "<function=" in text:
        return True
    if _INTERNAL_PHRASES.search(text):
        return True
    if _TOOL_NAME_LEAK.search(text):
        return True
    return False
