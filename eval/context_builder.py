# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/context_builder.py
-----------------------
Build RAGAS-ready context strings from agent responses.
Prefers actual retrieved chunk text over path-only stubs.
"""
from __future__ import annotations

from typing import Any

SENTINEL_NO_CONTEXT = "(no context retrieved)"


def _format_hit_context(hit: dict[str, Any]) -> str | None:
    chunk = (hit.get("chunk") or hit.get("snippet") or "").strip()
    if not chunk:
        return None
    fp = hit.get("file_path") or ""
    fn = hit.get("function_name") or ""
    lines = hit.get("lines")
    if lines is None and hit.get("start_line") is not None:
        end = hit.get("end_line")
        start = hit.get("start_line")
        lines = f"{start}-{end}" if end and end != start else str(start)
    header = f"File: {fp}"
    if fn:
        header += f"\nSymbol: {fn}"
    if lines:
        header += f"\nLines: {lines}"
    return f"{header}\n{chunk}"


def build_ragas_contexts(res: dict[str, Any]) -> tuple[list[str], bool]:
    """
    Return (context_strings, used_sentinel).
    Order: trace documents → retrieval_hits chunks → source snippets.
    """
    ctx_list: list[str] = []

    for it in res.get("trace", []):
        for doc in it.get("documents", []):
            content = doc.get("content", "")
            if content:
                ctx_list.append(content)

    if not ctx_list:
        for hit in res.get("retrieval_hits", []):
            formatted = _format_hit_context(hit)
            if formatted:
                ctx_list.append(formatted)

    if not ctx_list:
        for s in res.get("sources", []):
            snippet = (s.get("snippet") or s.get("chunk") or "").strip()
            fp = s.get("file_path", "")
            fn = s.get("function_name", "")
            if snippet:
                ctx_list.append(f"File: {fp}\nSymbol: {fn}\n{snippet}".strip())
            elif fp:
                ctx_list.append(f"File: {fp}\nSymbol: {fn}".strip())

    if not ctx_list:
        return [SENTINEL_NO_CONTEXT], True
    return ctx_list, False
