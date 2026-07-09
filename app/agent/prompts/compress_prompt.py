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


def compress_prompt(old_results: list[Any]) -> str:
    """
    Build a compression prompt for older tool outputs.

    Included: serialized older tool-result payloads only.
    Excluded: user question, latest tool results, retrieval chunks, decide/finalize text.
    """
    lines = [
        "Summarize the following older tool outputs into one dense, fact-rich paragraph.",
        "Preserve every file path, function name, line number, and relationship mentioned.",
        "Discard JSON boilerplate and repeated whitespace.",
        "Do not add information that is not present in the outputs.",
        "Target length: 120-250 words.",
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
        lines.append(f"--- Tool Output {i} ---")
        lines.append(payload[:4000])
        lines.append("")

    return "\n".join(lines).strip()
