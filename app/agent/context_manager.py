"""
app/agent/context_manager.py
----------------------------
Context compression and token management for the agent loop.
"""

import json
from typing import Any

from app.agent.llm_client import get_llm_client, RateLimitError
from app.observability.logging_config import logger


def compress_older_tool_results(messages: list[dict[str, Any]], keep_last_n: int = 2) -> None:
    """
    Summarize older tool results to prevent "slow bleed" context exhaustion.
    
    Many medium-sized tool outputs accumulating turn over turn silently exhaust
    the context budget by turn 7-8 even though no single turn looks expensive.
    This replaces old tool_use results with a dense paragraph summary.
    """
    # 1. Identify where the tool calls are in the history
    # We will find all user messages that contain `tool_result` blocks.
    tool_result_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_result_indices.append(i)
                    break
                    
    # If we don't have enough to compress, do nothing.
    if len(tool_result_indices) <= keep_last_n:
        return

    # Compress the older ones
    llm = get_llm_client()
    indices_to_compress = tool_result_indices[:-keep_last_n]
    
    # Combine all older tool outputs into a single prompt to save LLM calls
    combined_outputs = []
    for idx in indices_to_compress:
        combined_outputs.append(json.dumps(messages[idx]["content"]))
    
    prompt = (
        "Summarize each of the following tool outputs into a separate, dense, fact-rich paragraph. "
        "Keep all specific names, file paths, line numbers, and relationships, "
        "but discard the boilerplate JSON and formatting.\n\n"
    )
    for i, out in enumerate(combined_outputs):
        prompt += f"--- Tool Output {i+1} ---\n{out}\n\n"
        
    try:
        res = llm.create(
            system="You are an expert summarizer.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        summary_text = res.content[0]["text"] if res.content and res.content[0]["type"] == "text" else ""
        if summary_text:
            # Place the combined summary in the first message, and placeholder in others
            messages[indices_to_compress[0]]["content"] = [{
                "type": "text",
                "text": f"[Compressed prior tool results]: {summary_text}"
            }]
            for idx in indices_to_compress[1:]:
                messages[idx]["content"] = [{
                    "type": "text",
                    "text": "[Compressed prior tool results: see summary in previous turns]"
                }]
    except RateLimitError as e:
        logger.warning("context_compression_rate_limited", error=str(e))
        # Skip compression, leave messages uncompressed
        pass
    except Exception as e:
        logger.warning("context_compression_failed", error=str(e))
        # Leave it alone if compression fails
        pass
