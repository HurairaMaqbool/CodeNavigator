# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/compress_prompt.py
------------------------------------
OBSERVE/compress prompt — pure string builder, zero LLM/network calls.

Consumed by app/agent/context_manager.py when the token budget is exceeded.
"""
from __future__ import annotations

import json
from typing import Any


from app.agent.prompts.loader import load_private_prompt

_FALLBACK_COMPRESS_PROMPT = """Summarize the following older tool outputs into one dense, fact-rich paragraph.
Preserve every file path, function name, line number, and relationship mentioned.
Discard JSON boilerplate and repeated whitespace.
Do not add information that is not present in the outputs.
Target length: 120-250 words."""


def compress_prompt(old_results: list[Any]) -> str:
    """
    Build a compression prompt for older tool outputs.
    """
    template = load_private_prompt("compress_prompt.txt", _FALLBACK_COMPRESS_PROMPT)
    lines = [
        template,
        "",
    ]

    for i, item in enumerate(old_results, start=1):
        if isinstance(item, str):
            payload = item
        else:
            try:
                payload = json.dumps(item, ensure_ascii=False)
            except TypeError:
                payload = str(item)
            except NameError:
                import json
                payload = json.dumps(item, ensure_ascii=False)
        lines.append(f"--- Tool Output {i} ---")
        lines.append(payload[:4000])
        lines.append("")

    return "\n".join(lines).strip()
