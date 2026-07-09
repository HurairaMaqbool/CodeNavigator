# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/context_manager.py
----------------------------
Module #25 — OBSERVE-state token-budget enforcement and tool-result compression.

Uses ``tiktoken`` (``cl100k_base``, via ``chunker.get_token_count``) for deterministic
token estimates aligned with English/code Groq context accounting.

Fixed per-state budget — never a "near the limit" ratio heuristic.
"""
from __future__ import annotations

import concurrent.futures
import json
from typing import Any

from app.agent.llm_client import RateLimitError, get_llm_client
from app.agent.prompts import compress_prompt
from app.observability.logging_config import logger
from app.parsing.chunker import get_token_count

# Fixed OBSERVE tool-result budget (read once at import).
# loop.py uses 4000 tokens for assembled retrieval context; the same ceiling here
# keeps total OBSERVE footprint predictable (~8k tokens) with headroom for DECIDE,
# FINALIZE, and system prompts inside Groq's 128k context window.
OBSERVE_TOOL_RESULT_TOKEN_BUDGET: int = 4000

# Most recent tool results always stay verbatim for accuracy.
KEEP_RECENT_TOOL_RESULTS: int = 2

_COMPRESSION_TIMEOUT_S: float = 4.0
_COMPRESSION_MAX_ATTEMPTS: int = 2
_COMPRESSION_MAX_OUTPUT_TOKENS: int = 1000

_COMPRESSED_PREFIX = "[Compressed prior tool results]"
_PLACEHOLDER_TEXT = "[Compressed prior tool results: see summary in previous turns]"


# ---------------------------------------------------------------------------
# Token accounting
# ---------------------------------------------------------------------------

def _entry_text(entry: dict[str, Any]) -> str:
    content = entry.get("content")
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    if content is None:
        return ""
    return str(content)


def _entry_token_count(entry: dict[str, Any]) -> int:
    if "token_count" in entry:
        return max(0, int(entry["token_count"]))
    return get_token_count(_entry_text(entry))


def memory_token_count(memory: list[dict[str, Any]]) -> int:
    """Sum token counts across all working-memory entries."""
    return sum(_entry_token_count(entry) for entry in memory)


def _refresh_entry_token_count(entry: dict[str, Any]) -> None:
    entry["token_count"] = get_token_count(_entry_text(entry))


# ---------------------------------------------------------------------------
# Module #25 public API
# ---------------------------------------------------------------------------

def should_compress(memory: list[dict[str, Any]]) -> bool:
    """
    Deterministic budget check — True when accumulated tool-result tokens exceed
    ``OBSERVE_TOOL_RESULT_TOKEN_BUDGET``.
    """
    if not memory:
        return False
    return memory_token_count(memory) > OBSERVE_TOOL_RESULT_TOKEN_BUDGET


def compress(memory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Condense oldest tool-result entries when the fixed budget is exceeded.

    Returns the same list object with older entries replaced by summaries.
    Most recent ``KEEP_RECENT_TOOL_RESULTS`` entries remain verbatim.
    """
    if not memory or len(memory) <= KEEP_RECENT_TOOL_RESULTS:
        return memory
    if not should_compress(memory):
        return memory
    _compress_oldest_entries(memory, KEEP_RECENT_TOOL_RESULTS)
    return memory


# ---------------------------------------------------------------------------
# Compression internals
# ---------------------------------------------------------------------------

def _tool_result_indices(messages: list[dict[str, Any]]) -> list[int]:
    indices: list[int] = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    indices.append(i)
                    break
    return indices


def _serialize_for_prompt(entry: dict[str, Any]) -> Any:
    return entry.get("content", entry)


def _call_compression_llm(prompt: str) -> str | None:
    """
    Bounded Groq compression call — timeout + retry-once (query_expansion pattern).

    Returns summary text on success, ``None`` when compression failed (exception,
    timeout, or empty response). A legitimately short non-empty summary is success.
    """
    llm = get_llm_client()
    last_exc: Exception | None = None

    for attempt in range(_COMPRESSION_MAX_ATTEMPTS):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    llm.create,
                    system="You are an expert summarizer.",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=_COMPRESSION_MAX_OUTPUT_TOKENS,
                )
                res = future.result(timeout=_COMPRESSION_TIMEOUT_S)

            if not res.content:
                last_exc = ValueError("empty_llm_content")
                continue

            block = res.content[0]
            if block.get("type") != "text":
                last_exc = ValueError("non_text_llm_block")
                continue

            summary = str(block.get("text", "")).strip()
            if summary:
                return summary

            last_exc = ValueError("empty_summary_text")
        except RateLimitError as exc:
            last_exc = exc
            logger.warning(
                "context_compression_rate_limited",
                attempt=attempt + 1,
                error=str(exc),
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "context_compression_attempt_failed",
                attempt=attempt + 1,
                error=str(exc),
            )

    logger.warning("context_compression_failed_all_attempts", error=str(last_exc))
    return None


def _apply_summary_to_entries(
    memory: list[dict[str, Any]],
    *,
    summary_text: str,
    compress_count: int,
    keep_recent: int,
) -> None:
    """Replace the oldest ``compress_count`` entries with summary + placeholders."""
    if compress_count <= 0:
        return

    first = memory[0]
    first["content"] = [{
        "type": "text",
        "text": f"{_COMPRESSED_PREFIX}: {summary_text}",
    }]
    if "role" in first:
        first["role"] = first.get("role", "user")
    _refresh_entry_token_count(first)

    for idx in range(1, compress_count):
        entry = memory[idx]
        entry["content"] = [{"type": "text", "text": _PLACEHOLDER_TEXT}]
        _refresh_entry_token_count(entry)

    _ = keep_recent  # recent tail entries at memory[-keep_recent:] stay untouched


def _drop_oldest_entry(memory: list[dict[str, Any]]) -> None:
    """Naive truncation fallback — remove the single oldest entry."""
    if memory:
        memory.pop(0)
        logger.info("context_compression_fallback_truncation")


def _compress_oldest_entries(memory: list[dict[str, Any]], keep_recent: int) -> bool:
    """
    Compress oldest entries in ``memory``.

    Returns True when fallback truncation dropped the oldest entry.
    """
    if len(memory) <= keep_recent:
        return False

    compress_count = len(memory) - keep_recent
    old_results = [_serialize_for_prompt(entry) for entry in memory[:compress_count]]
    prompt = compress_prompt(old_results)

    summary = _call_compression_llm(prompt)
    if summary:
        _apply_summary_to_entries(
            memory,
            summary_text=summary,
            compress_count=compress_count,
            keep_recent=keep_recent,
        )
        logger.info(
            "context_compression_applied",
            compressed_entries=compress_count,
            kept_recent=keep_recent,
        )
        return False

    _drop_oldest_entry(memory)
    return True


# ---------------------------------------------------------------------------
# Legacy compatibility (Module 9a / loop re-export)
# ---------------------------------------------------------------------------

def compress_older_tool_results(messages: list[dict[str, Any]], keep_last_n: int = 2) -> None:
    """
    Legacy entry point — compress older tool-result messages when count exceeds
    ``keep_last_n``, regardless of token budget (Module 9a EC9 behavior).
    """
    indices = _tool_result_indices(messages)
    if len(indices) <= keep_last_n:
        return

    subset = [messages[i] for i in indices]
    truncated = _compress_oldest_entries(subset, keep_last_n)
    if truncated:
        del messages[indices[0]]


def assemble_context(
    chunks: list[dict[str, Any]],
    graph_context: str,
    *,
    max_tokens: int = OBSERVE_TOOL_RESULT_TOKEN_BUDGET,
) -> str:
    """
    Trim merged retrieval chunks to a token budget for DECIDE/FINALIZE.

    Complements tool-result compression; uses the same 4-char/token heuristic as loop.py.
    """
    budget_chars = max(500, max_tokens * 4)
    parts: list[str] = []
    used = 0
    for hit in chunks:
        text = hit.get("chunk") or ""
        if not text:
            continue
        meta = hit.get("chunk_metadata") or hit.get("metadata") or {}
        header = meta.get("display_path") or meta.get("file_path") or "chunk"
        block = f"### {header}\n{text}"
        if used + len(block) > budget_chars:
            remaining = budget_chars - used
            if remaining > 80:
                parts.append(block[:remaining] + "\n...[truncated]")
            break
        parts.append(block)
        used += len(block)
    if graph_context:
        parts.append(f"### Graph context\n{graph_context[:2000]}")
    return "\n\n".join(parts) if parts else "(no context retrieved)"
