# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/context_builder.py
-----------------------
Build RAGAS-ready context strings from agent responses.
Prefers actual retrieved chunk text over path-only stubs.
Automatically hydrates missing code snippets from file paths on disk.
Caps snippet length at 25 lines / 2000 chars to avoid Groq 6000 TPM HTTP 413 limits.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SENTINEL_NO_CONTEXT = "(no context retrieved)"
MAX_SNIPPET_LINES = 25
MAX_SNIPPET_CHARS = 2000


def _hydrate_file_snippet(file_path: str, lines_str: str | None = None) -> str:
    """Read actual code text from disk for a given file_path and optional line range (e.g. '10-45')."""
    if not file_path:
        return ""
    p = Path(file_path)
    if not p.exists():
        p = Path.cwd() / file_path
    if not p.exists():
        return ""
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        res_text = ""
        if lines_str:
            parts = str(lines_str).split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start, end = int(parts[0]), int(parts[1])
                # Cap slice at MAX_SNIPPET_LINES
                end = min(end, start + MAX_SNIPPET_LINES - 1)
                sliced = lines[max(0, start - 1): min(len(lines), end)]
                res_text = "\n".join(sliced)
                if start > 15 and len(lines) > 12:
                    head_lines = lines[:12]
                    head_str = "\n".join(head_lines).strip()
                    if len(head_str) > 400:
                        head_str = head_str[:400] + "\n..."
                    res_text = f"# File Header (Imports & Constants):\n{head_str}\n\n# Code Snippet (Lines {start}-{end}):\n{res_text}"
            elif len(parts) == 1 and parts[0].isdigit():
                idx = int(parts[0]) - 1
                if 0 <= idx < len(lines):
                    res_text = lines[idx]
        if not res_text:
            res_text = "\n".join(lines[:MAX_SNIPPET_LINES])
        
        if len(res_text) > MAX_SNIPPET_CHARS:
            res_text = res_text[:MAX_SNIPPET_CHARS] + "\n..."
        return res_text
    except Exception:
        return ""


def _format_hit_context(hit: dict[str, Any]) -> str | None:
    fp = hit.get("file_path") or hit.get("path") or ""
    fn = hit.get("function_name") or hit.get("symbol") or hit.get("fn") or ""
    lines = hit.get("lines")
    if lines is None and hit.get("start_line") is not None:
        end = hit.get("end_line")
        start = hit.get("start_line")
        lines = f"{start}-{end}" if end and end != start else str(start)

    chunk = (hit.get("chunk") or hit.get("snippet") or hit.get("content") or "").strip()
    if not chunk and fp:
        chunk = _hydrate_file_snippet(fp, str(lines) if lines else None)
    elif chunk and len(chunk) > MAX_SNIPPET_CHARS:
        chunk = chunk[:MAX_SNIPPET_CHARS] + "\n..."

    if not chunk and not fp:
        return None

    header = f"File: {fp}"
    if fn:
        header += f"\nSymbol: {fn}"
    if lines:
        header += f"\nLines: {lines}"
    
    return f"{header}\n{chunk}".strip() if chunk else f"{header}".strip()


def build_ragas_contexts(res: dict[str, Any]) -> tuple[list[str], bool]:
    """
    Return (context_strings, used_sentinel).
    Order: trace documents → retrieval_hits chunks → source snippets.
    Guarantees actual factual code text is populated for RAGAS metrics.
    Capped to prevent Groq HTTP 413 Payload Too Large.
    """
    ctx_list: list[str] = []

    # 1. Try trace documents
    for it in res.get("trace", []):
        for doc in it.get("documents", []):
            content = (doc.get("content") or doc.get("chunk") or doc.get("snippet") or "").strip()
            fp = doc.get("file_path") or doc.get("path") or ""
            lines = doc.get("lines")
            if not content and fp:
                content = _hydrate_file_snippet(fp, str(lines) if lines else None)
            elif content and len(content) > MAX_SNIPPET_CHARS:
                content = content[:MAX_SNIPPET_CHARS] + "\n..."
            if content:
                ctx_list.append(f"File: {fp}\n{content}".strip() if fp else content)

    # 2. Try retrieval_hits
    if not ctx_list:
        for hit in res.get("retrieval_hits", []):
            formatted = _format_hit_context(hit)
            if formatted:
                ctx_list.append(formatted)

    # 3. Try sources
    if not ctx_list:
        for s in res.get("sources", []):
            formatted = _format_hit_context(s)
            if formatted:
                ctx_list.append(formatted)

    if not ctx_list:
        return [SENTINEL_NO_CONTEXT], True
    return ctx_list, False
