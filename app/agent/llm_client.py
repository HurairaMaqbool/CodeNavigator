# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/llm_client.py
-----------------------
LLM Provider Abstraction Layer.

Responsibility boundary
-----------------------
This is the ONLY module in the codebase allowed to know about wire-level
provider differences. It normalizes all API interaction into a single interface.
It does NOT:
  - execute agent loops (Module 9),
  - store or execute tools (Module 9),
  - define system prompts (Module 9).

Why normalize to Anthropic-style blocks?
----------------------------------------
OpenAI/Groq represents tools as an array of tool_calls on the message.
Anthropic represents them as heterogeneous text blocks and tool_use blocks
in the content array. We standardize on the Anthropic shape internally because
it is strict and prevents ambiguous mixed-text-and-tool payloads from confusing
the agent loop.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.observability.logging_config import logger

# ---------------------------------------------------------------------------
# Core Normalized Shapes
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """
    Normalized response shape across all providers.
    """
    content: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, int]


class RateLimitError(Exception):
    """Raised when the provider rate limits us (429), explicitly retryable."""
    pass


class ProviderError(Exception):
    """Raised when the provider fails for an unknown reason."""
    pass


# ---------------------------------------------------------------------------
# Tool Schema Translation
# ---------------------------------------------------------------------------

def _translate_anthropic_tools_to_openai(anthropic_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert Anthropic-style tools to OpenAI/Groq-style tools.
    
    Anthropic:
    {
      "name": "search_code",
      "description": "...",
      "input_schema": {
        "type": "object",
        "properties": {...},
        "required": [...]
      }
    }
    
    OpenAI:
    {
      "type": "function",
      "function": {
        "name": "search_code",
        "description": "...",
        "parameters": {
          "type": "object",
          "properties": {...},
          "required": [...]
        }
      }
    }
    """
    openai_tools = []
    for t in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}})
            }
        })
    return openai_tools


def _translate_anthropic_tools_to_ollama(anthropic_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ollama uses exactly the OpenAI format for tool definitions.
    """
    return _translate_anthropic_tools_to_openai(anthropic_tools)


def _translate_anthropic_messages_to_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    openai_msgs = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        
        if isinstance(content, str):
            openai_msgs.append({"role": role, "content": content})
            continue
            
        if role == "assistant":
            text_str = ""
            t_calls = []
            for b in content:
                if b["type"] == "text":
                    text_str += b["text"] + "\n"
                elif b["type"] == "tool_use":
                    t_calls.append({
                        "id": b["id"],
                        "type": "function",
                        "function": {
                            "name": b["name"],
                            "arguments": json.dumps(b["input"]) if isinstance(b["input"], dict) else b["input"]
                        }
                    })
            new_msg = {"role": "assistant"}
            # Groq API requires content to be a valid string, even if empty.
            new_msg["content"] = text_str.strip() if text_str.strip() else ""
            if t_calls:
                new_msg["tool_calls"] = t_calls
            openai_msgs.append(new_msg)
            
        elif role == "user":
            text_str = ""
            for b in content:
                if b["type"] == "text":
                    text_str += b["text"] + "\n"
                elif b["type"] == "tool_result":
                    openai_msgs.append({
                        "role": "tool",
                        "tool_call_id": b.get("tool_use_id", ""),
                        "content": str(b.get("content", ""))
                    })
            if text_str:
                openai_msgs.append({"role": "user", "content": text_str.strip()})
    return openai_msgs


# ---------------------------------------------------------------------------
# Groq text-tool recovery (model sometimes leaks <function=...> in plain text)
# ---------------------------------------------------------------------------

_FUNCTION_TAG_PREFIX = re.compile(r"<function=([a-zA-Z0-9_-]+)>\s*")


def _parse_json_object_at(text: str, start: int) -> tuple[dict[str, Any] | None, int]:
    if start >= len(text) or text[start] != "{":
        return None, start
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1]), i + 1
                except json.JSONDecodeError:
                    return None, i + 1
    return None, len(text)


def parse_groq_function_tags(text: str) -> tuple[list[dict[str, Any]], str]:
    """
    Promote Groq/Llama text leaks like
    `<function=search_code>{"query": "foo", "top_k": 2}</function>`
    into normalized tool_use blocks.
    """
    if not text or "<function=" not in text:
        return [], text

    tool_blocks: list[dict[str, Any]] = []
    remainder_parts: list[str] = []
    i = 0

    while i < len(text):
        match = _FUNCTION_TAG_PREFIX.search(text, i)
        if not match:
            remainder_parts.append(text[i:])
            break

        remainder_parts.append(text[i : match.start()])
        tool_name = match.group(1)
        brace = text.find("{", match.end())
        if brace == -1:
            i = match.end()
            continue

        tool_input, end_pos = _parse_json_object_at(text, brace)
        if tool_input is None:
            i = match.end()
            continue

        tool_blocks.append({
            "type": "tool_use",
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "name": tool_name,
            "input": tool_input,
        })
        i = end_pos
        close = text.find("</function>", i)
        if 0 <= close - i < 30:
            i = close + len("</function>")

    remainder = "".join(remainder_parts).strip()
    return tool_blocks, remainder


def _coerce_groq_text_tools(content_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in content_blocks:
        if block.get("type") != "text":
            out.append(block)
            continue
        tools, remainder = parse_groq_function_tags(block.get("text", ""))
        out.extend(tools)
        if remainder:
            out.append({"type": "text", "text": remainder})
    return out


class GroqAdapter:
    """Wraps the Groq SDK."""
    def __init__(self, api_key: str, model: str):
        try:
            from groq import Groq, RateLimitError as GroqRateLimitError
            from groq import APIStatusError, APITimeoutError
            self._client = Groq(api_key=api_key)
            self._model = model
            self._groq_errors = (GroqRateLimitError, APIStatusError, APITimeoutError)
        except ImportError:
            raise ImportError("The 'groq' package is not installed.")

    def create(self, system: str, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 1024) -> LLMResponse:
        from groq import RateLimitError as GroqRateLimitError
        from groq import APITimeoutError
        
        # 1. Translate tools
        groq_tools = _translate_anthropic_tools_to_openai(tools) if tools else None

        # 2. Prepend system message and translate to OpenAI format
        translated_messages = _translate_anthropic_messages_to_openai(messages)
        api_messages = [{"role": "system", "content": system}] + translated_messages

        # 3. Call API
        try:
            kwargs = {
                "model": self._model,
                "messages": api_messages,
                "max_tokens": max_tokens,
            }
            if groq_tools:
                kwargs["tools"] = groq_tools
                # "auto" means the model decides.
                kwargs["tool_choice"] = "auto"
                
            from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
            
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                retry=retry_if_exception_type((GroqRateLimitError, APITimeoutError)),
                reraise=True
            )
            def _call_groq():
                return self._client.chat.completions.create(**kwargs)
            
            res = _call_groq()

        except GroqRateLimitError as e:
            logger.warning("groq_rate_limit", error=str(e))
            raise RateLimitError("Groq API rate limit exceeded.") from e
        except APITimeoutError as e:
            logger.warning("groq_timeout", error=str(e))
            raise RateLimitError("Groq API timed out (treat as retryable).") from e
        except Exception as e:
            # Try to recover from tool_use_failed errors by parsing the malformed XML tag from failed_generation.
            try:
                failed_gen = None
                body = getattr(e, "body", None)
                if isinstance(body, dict):
                    err_info = body.get("error", {})
                    if err_info.get("code") == "tool_use_failed":
                        failed_gen = err_info.get("failed_generation")
                
                if not failed_gen:
                    e_str = str(e)
                    if "tool_use_failed" in e_str:
                        start_idx = e_str.find("{")
                        if start_idx != -1:
                            end_idx = e_str.rfind("}")
                            if end_idx != -1 and end_idx > start_idx:
                                try:
                                    err_dict = json.loads(e_str[start_idx:end_idx+1])
                                    failed_gen = err_dict.get("error", {}).get("failed_generation")
                                except Exception:
                                    pass

                if failed_gen:
                    tools, _ = parse_groq_function_tags(failed_gen)
                    if tools:
                        logger.info(
                            "recovered_groq_tool_call",
                            tool_name=tools[0]["name"],
                            tool_input=tools[0]["input"],
                        )
                        return LLMResponse(
                            content=tools,
                            stop_reason="tool_use",
                            usage={"input_tokens": 0, "output_tokens": 0},
                        )
                    import re
                    match = re.search(r"<function=([a-zA-Z0-9_-]+)", failed_gen)
                    if match:
                        tool_name = match.group(1)
                        start_bracket = failed_gen.find("{", match.end())
                        if start_bracket != -1:
                            # 1. Try parsing everything from first '{' to last '}'
                            end_bracket = failed_gen.rfind("}")
                            if end_bracket != -1 and end_bracket > start_bracket:
                                json_part = failed_gen[start_bracket:end_bracket+1]
                                try:
                                    tool_input = json.loads(json_part)
                                    import uuid
                                    tool_id = f"call_{uuid.uuid4().hex[:8]}"
                                    logger.info("recovered_groq_tool_call", tool_name=tool_name, tool_input=tool_input)
                                    return LLMResponse(
                                        content=[{
                                            "type": "tool_use",
                                            "id": tool_id,
                                            "name": tool_name,
                                            "input": tool_input
                                        }],
                                        stop_reason="tool_use",
                                        usage={"input_tokens": 0, "output_tokens": 0}
                                    )
                                except Exception:
                                    # 2. Fallback bracket counting to parse a prefix of failed_gen
                                    bracket_count = 0
                                    for i in range(start_bracket, len(failed_gen)):
                                        char = failed_gen[i]
                                        if char == "{":
                                            bracket_count += 1
                                        elif char == "}":
                                            bracket_count -= 1
                                            if bracket_count == 0:
                                                try:
                                                    tool_input = json.loads(failed_gen[start_bracket:i+1])
                                                    import uuid
                                                    tool_id = f"call_{uuid.uuid4().hex[:8]}"
                                                    logger.info("recovered_groq_tool_call_fallback", tool_name=tool_name, tool_input=tool_input)
                                                    return LLMResponse(
                                                        content=[{
                                                            "type": "tool_use",
                                                            "id": tool_id,
                                                            "name": tool_name,
                                                            "input": tool_input
                                                        }],
                                                        stop_reason="tool_use",
                                                        usage={"input_tokens": 0, "output_tokens": 0}
                                                    )
                                                except Exception:
                                                    pass
            except Exception as recovery_err:
                logger.warning("groq_recovery_failed", error=str(recovery_err))

            logger.error("groq_unknown_error", error=str(e))
            raise ProviderError(f"Groq API error: {str(e)}") from e

        # 4. Normalize response
        choice = res.choices[0]
        msg = choice.message
        stop_reason = choice.finish_reason

        # Normalize stop reason
        # Groq stop reasons: "stop", "tool_calls", "length", "failed"
        if stop_reason == "tool_calls":
            norm_stop = "tool_use"
        elif stop_reason in ("stop", "length"):
            # If it's stop but there are tool calls, sometimes APIs are weird.
            if msg.tool_calls:
                norm_stop = "tool_use"
            else:
                norm_stop = "end_turn"
        else:
            norm_stop = "end_turn"

        content_blocks = []
        
        # Add text block if present
        if msg.content:
            content_blocks.append({
                "type": "text",
                "text": msg.content
            })

        # Add tool_use blocks if present
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.type == "function":
                    try:
                        input_dict = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        # Don't try to silently fix malformed JSON.
                        # We pass it back honestly, but we must make sure it's an object or string.
                        # If the agent wants to recover, the agent loops handles error feedback.
                        input_dict = tc.function.arguments

                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": input_dict
                    })

        content_blocks = _coerce_groq_text_tools(content_blocks)
        if any(b.get("type") == "tool_use" for b in content_blocks):
            norm_stop = "tool_use"

        usage_dict = {
            "input_tokens": res.usage.prompt_tokens if res.usage else 0,
            "output_tokens": res.usage.completion_tokens if res.usage else 0,
        }

        return LLMResponse(
            content=content_blocks,
            stop_reason=norm_stop,
            usage=usage_dict
        )

    def generate_text(self, prompt: str) -> str:
        res = self.create(
            system="You are an expert software engineer.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512
        )
        if res.content and res.content[0]["type"] == "text":
            return res.content[0]["text"]
        return ""


class OllamaAdapter:
    """Wraps local Ollama API."""
    def __init__(self, base_url: str, model: str):
        try:
            import httpx
        except ImportError:
            raise ImportError("The 'httpx' package is required for Ollama.")
            
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=120.0)

    def create(self, system: str, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 1024) -> LLMResponse:
        import httpx
        
        ollama_tools = _translate_anthropic_tools_to_ollama(tools) if tools else None

        # Ollama system prompt is natively supported as a "system" role message
        translated_messages = _translate_anthropic_messages_to_openai(messages)
        api_messages = [{"role": "system", "content": system}] + translated_messages

        payload = {
            "model": self.model,
            "messages": api_messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens
            }
        }
        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            response = self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as e:
            logger.error("ollama_connection_failed", base_url=self.base_url, error=str(e))
            raise ProviderError(
                f"Ollama server unreachable at {self.base_url}. Ensure it is running locally."
            ) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Ollama rate limit.") from e
            raise ProviderError(f"Ollama API HTTP {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise ProviderError(f"Ollama unknown error: {str(e)}") from e

        msg = data.get("message", {})
        
        # Ollama finish reasons: "stop", "tool_calls"
        done_reason = data.get("done_reason", "stop")
        
        tool_calls = msg.get("tool_calls", [])
        
        if done_reason == "tool_calls" or tool_calls:
            norm_stop = "tool_use"
        else:
            norm_stop = "end_turn"

        content_blocks = []
        if msg.get("content"):
            content_blocks.append({
                "type": "text",
                "text": msg.get("content")
            })

        # Known Tradeoff: Smaller local models are less reliable at multi-step tool calling.
        # We DO NOT silently fix unreliable tool-call JSON output.
        # If it returns malformed calls, we honestly represent it so Module 9 handles the error.
        import uuid
        for tc in tool_calls:
            func = tc.get("function", {})
            args = func.get("arguments", {})
            
            # If Ollama doesn't return an ID, generate one so our schema holds
            tc_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            
            content_blocks.append({
                "type": "tool_use",
                "id": tc_id,
                "name": func.get("name", ""),
                "input": args
            })

        usage_dict = {
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0)
        }

        return LLMResponse(
            content=content_blocks,
            stop_reason=norm_stop,
            usage=usage_dict
        )

    def generate_text(self, prompt: str) -> str:
        res = self.create(
            system="You are an expert software engineer.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512
        )
        if res.content and res.content[0]["type"] == "text":
            return res.content[0]["text"]
        return ""

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_client() -> GroqAdapter | OllamaAdapter:
    """
    Factory to return the configured LLM client abstraction.
    Raises ValueError immediately if the configured provider is unrecognized.
    """
    provider = settings.LLM_PROVIDER.strip().lower()

    if provider == "groq":
        return GroqAdapter(
            api_key=settings.GROQ_API_KEY,
            model=settings.LLM_MODEL
        )
    elif provider == "ollama":
        return OllamaAdapter(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.LLM_MODEL
        )
    else:
        raise ValueError(f"Unrecognized LLM_PROVIDER in settings: '{provider}'. Must be 'groq' or 'ollama'.")
