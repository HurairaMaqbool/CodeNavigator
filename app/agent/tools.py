# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/tools.py
------------------
Module #22 — Tool execution and schema validation for loop.py ACT state.

Schema approach: **Pydantic v2 models** per tool — the project already depends on
Pydantic; models give strict type/required-field checks and export JSON Schema
for ``TOOL_DEFINITIONS`` without maintaining two parallel schema sources.

Forward interface contract (ACT/OBSERVE consumer):
    execute(...) -> {tool_name, result, success, error}
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Type

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.config import settings
from app.graph.queries import get_dependencies, get_dependents
from app.observability.logging_config import logger

# Transient I/O errors eligible for retry (max 2 retries in execute()).
_TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    OSError,
    TimeoutError,
    ConnectionError,
    BlockingIOError,
    urllib.error.URLError,
)


class ToolValidationError(ValueError):
    """Raised by validate_call when tool_name or arguments are invalid."""


# ---------------------------------------------------------------------------
# Pydantic argument models (one per spec tool)
# ---------------------------------------------------------------------------

class SearchCodeArgs(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class ReadFileArgs(BaseModel):
    file_path: str = Field(min_length=1)


class GraphNameArgs(BaseModel):
    name: str = Field(min_length=1)


class GenerateDiagramArgs(BaseModel):
    name: str = Field(min_length=1)
    depth: int = Field(default=2, ge=1, le=10)


class SearchWebDocsArgs(BaseModel):
    query: str = Field(min_length=1)


class GetSubgraphArgs(BaseModel):
    name: str = Field(min_length=1)
    depth: int = Field(default=2, ge=1, le=10)


_TOOL_MODELS: dict[str, Type[BaseModel]] = {
    "search_code": SearchCodeArgs,
    "read_file": ReadFileArgs,
    "get_callers": GraphNameArgs,
    "get_callees": GraphNameArgs,
    "generate_diagram": GenerateDiagramArgs,
}

_LEGACY_TOOL_MODELS: dict[str, Type[BaseModel]] = {
    "search_web_docs": SearchWebDocsArgs,
    "get_subgraph": GetSubgraphArgs,
}

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_code": "Search the codebase semantically and via keyword. Returns ranked snippets.",
    "read_file": "Read the contents of a specific file from the cloned repo (path-jailed).",
    "get_callers": "Find functions that call the named symbol (graph dependents).",
    "get_callees": "Find functions the named symbol calls (graph dependencies).",
    "generate_diagram": "Generate a Mermaid call-graph diagram from a function entry point.",
    "search_web_docs": "Search the web for external documentation (legacy).",
    "get_subgraph": "Traverse the call graph outward from a function (legacy).",
}


def _schema_from_model(model: Type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    props = schema.get("properties", {})
    required = schema.get("required", [])
    return {"type": "object", "properties": props, "required": required}


def _build_tool_definitions() -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    for name, model in {**_TOOL_MODELS, **_LEGACY_TOOL_MODELS}.items():
        defs.append({
            "name": name,
            "description": _TOOL_DESCRIPTIONS[name],
            "input_schema": _schema_from_model(model),
        })
    return defs


TOOL_DEFINITIONS: list[dict[str, Any]] = _build_tool_definitions()


@dataclass(frozen=True)
class ValidatedCall:
    tool_name: str
    arguments: dict[str, Any]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_call(tool_name: str, arguments: dict[str, Any] | None) -> ValidatedCall:
    """
    Validate tool_name and arguments against the declared Pydantic schema.

    Raises ToolValidationError on unknown tool or schema mismatch — never dispatches.
    """
    if not isinstance(arguments, dict):
        raise ToolValidationError("arguments must be a JSON object")

    model = _TOOL_MODELS.get(tool_name)
    if model is None:
        raise ToolValidationError(f"Unknown tool: {tool_name}")

    try:
        parsed = model.model_validate(arguments)
    except PydanticValidationError as exc:
        raise ToolValidationError(f"Schema validation failed for {tool_name}: {exc}") from exc

    return ValidatedCall(tool_name=tool_name, arguments=parsed.model_dump())


def _validate_legacy(tool_name: str, arguments: dict[str, Any] | None) -> ValidatedCall:
    model = _LEGACY_TOOL_MODELS.get(tool_name)
    if model is None:
        raise ToolValidationError(f"Unknown tool: {tool_name}")
    if not isinstance(arguments, dict):
        raise ToolValidationError("arguments must be a JSON object")
    parsed = model.model_validate(arguments)
    return ValidatedCall(tool_name=tool_name, arguments=parsed.model_dump())


# ---------------------------------------------------------------------------
# Dispatch implementations (real downstream modules — no stubs)
# ---------------------------------------------------------------------------

def _format_search_hit(hit: dict[str, Any]) -> dict[str, Any]:
    meta = hit.get("chunk_metadata") or {}
    path_val = meta.get("display_path") or meta.get("file_path") or meta.get("normalized_path") or ""
    return {
        "chunk": hit.get("chunk") or "",
        "metadata": meta,
        "rerank_score": float(hit.get("score", 0.0)),
        "file_path": path_val,
    }


def _do_search_code(repo_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    from app.retrieval.hybrid_search import search
    from app.retrieval.reranker import rerank

    hits = search(repo_id, query, top_k=max(top_k * 2, 10))
    ranked = rerank(query, hits, top_n=top_k)

    max_chunk_len = 800 if settings.LLM_PROVIDER.lower() == "groq" else 1200
    results: list[dict[str, Any]] = []
    for hit in ranked:
        formatted = _format_search_hit(hit)
        chunk = formatted.get("chunk", "")
        if isinstance(chunk, str) and len(chunk) > max_chunk_len:
            formatted["chunk"] = chunk[:max_chunk_len] + "\n... [truncated, use read_file for full content] ..."
        meta = formatted.get("metadata", {})
        for path_key in ("file_path", "display_path", "normalized_path"):
            if path_key in meta and isinstance(meta[path_key], str):
                path_val = meta[path_key].replace("\\", "/").lstrip("/")
                clone_marker = "/clone/"
                clone_idx = path_val.find(clone_marker)
                if clone_idx != -1:
                    meta[path_key] = path_val[clone_idx + len(clone_marker):]
                else:
                    parts = path_val.split("/")
                    if len(parts) > 2 and parts[0] == "repos" and parts[2] == "clone":
                        meta[path_key] = "/".join(parts[3:])
        results.append(formatted)
    return {"results": results}


def _do_get_callers(repo_id: str, name: str) -> dict[str, Any]:
    return {"results": [{"caller": d, "name": d} for d in get_dependents(repo_id, name)]}


def _do_get_callees(repo_id: str, name: str) -> dict[str, Any]:
    return {"results": [{"callee": d, "name": d} for d in get_dependencies(repo_id, name)]}


def _do_read_file(repo_id: str, file_path: str) -> dict[str, Any]:
    from app.ingestion.file_filter import safe_decode
    from app.security.path_jail import PathJailError, resolve_jailed_path

    clone_root = Path(settings.REPOS_PATH) / repo_id / "clone"
    try:
        abs_path = resolve_jailed_path(clone_root, file_path)
    except PathJailError as exc:
        return {"error": str(exc)}

    if not abs_path.is_file():
        return {"error": f"File '{file_path}' not found or is not a file."}

    text, decode_error = safe_decode(abs_path)
    if decode_error is not None:
        return {"error": f"Failed to read file: {decode_error}"}

    content = text or ""
    lines = content.splitlines()
    limit = 150 if settings.LLM_PROVIDER.lower() == "groq" else 800
    if len(lines) > limit:
        rendered = "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines[:limit]))
        return {
            "content": rendered,
            "truncated": True,
            "instruction": f"File exceeded {limit} lines and was truncated. Use search_code to target specific parts.",
        }
    rendered = "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines))
    return {"content": rendered}


def _do_generate_diagram(repo_id: str, name: str, depth: int = 2) -> dict[str, Any]:
    from app.diagrams.mermaid_generator import generate_mermaid
    from app.graph.queries import get_subgraph

    sub = get_subgraph(repo_id, name, depth)
    sub_with_entry = {**sub, "entry_point": name}
    mermaid = generate_mermaid(sub_with_entry, direction="both", repo_id=repo_id)
    return {
        "mermaid": mermaid,
        "clamped": sub.get("clamped", False),
        "requested_depth": sub.get("requested_depth", depth),
    }


def _do_search_web_docs(repo_id: str, query: str) -> dict[str, Any]:
    _ = repo_id
    timeout = settings.SEARCH_WEB_DOCS_TIMEOUT_S
    import urllib.parse

    url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
        f"{urllib.parse.quote(query)}&utf8=&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode())
            snippets = [item["snippet"] for item in data.get("query", {}).get("search", [])[:3]]
            return {"results": snippets}
    except Exception as exc:
        logger.warning("web_search_failed", query=query, error=str(exc))
        msg = (
            f"web search timed out after {timeout}s"
            if isinstance(exc, TimeoutError)
            else f"web search failed: {exc}"
        )
        out: dict[str, Any] = {"error": msg}
        if isinstance(exc, TimeoutError):
            out["instruction"] = (
                "Do not retry this exact search. Proceed using existing codebase knowledge, "
                "or inform the user you could not reach external documentation for this query."
            )
        return out


def _do_get_subgraph(repo_id: str, name: str, depth: int = 2) -> dict[str, Any]:
    from app.graph.queries import get_subgraph

    return get_subgraph(repo_id, name, max_depth=depth)


def _dispatch_validated(call: ValidatedCall, repo_id: str) -> dict[str, Any]:
    name = call.tool_name
    args = call.arguments
    if name == "search_code":
        return _do_search_code(repo_id, args["query"], args.get("top_k", 5))
    if name == "read_file":
        return _do_read_file(repo_id, args["file_path"])
    if name == "get_callers":
        return _do_get_callers(repo_id, args["name"])
    if name == "get_callees":
        return _do_get_callees(repo_id, args["name"])
    if name == "generate_diagram":
        return _do_generate_diagram(repo_id, args["name"], args.get("depth", 2))
    if name == "search_web_docs":
        return _do_search_web_docs(repo_id, args["query"])
    if name == "get_subgraph":
        return _do_get_subgraph(repo_id, args["name"], args.get("depth", 2))
    return {"error": f"Unknown tool: {name}"}


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSIENT_EXCEPTIONS):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in {5, 11, 16}:
        return True
    return False


def _run_with_retries(
    fn: Callable[[], dict[str, Any]],
    *,
    tool_name: str,
    repo_id: str,
    max_retries: int,
) -> dict[str, Any]:
    log = logger.bind(tool_name=tool_name, repo_id=repo_id)
    attempts = max_retries + 1
    last_exc: BaseException | None = None

    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not _is_transient_error(exc) or attempt >= attempts - 1:
                log.warning("tool_execution_failed_final", error=str(exc), attempt=attempt + 1)
                return {"error": f"Tool execution failed: {exc}"}
            log.warning("tool_execution_transient_retry", error=str(exc), attempt=attempt + 1)
            time.sleep(0.5 * (attempt + 1))

    return {"error": f"Tool execution failed after retries: {last_exc}"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute(
    tool_name: str,
    arguments: dict[str, Any],
    repo_id: str,
    *,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    Validate and execute a tool call.

    Returns ``{tool_name, result, success, error}`` for ACT/OBSERVE consumption.
    """
    try:
        if tool_name in _LEGACY_TOOL_MODELS:
            validated = _validate_legacy(tool_name, arguments)
        else:
            validated = validate_call(tool_name, arguments)
    except ToolValidationError as exc:
        return {
            "tool_name": tool_name,
            "result": None,
            "success": False,
            "error": str(exc),
        }

    raw = _run_with_retries(
        lambda: _dispatch_validated(validated, repo_id),
        tool_name=tool_name,
        repo_id=repo_id,
        max_retries=max_retries,
    )

    if isinstance(raw, dict) and raw.get("error"):
        return {
            "tool_name": tool_name,
            "result": raw,
            "success": False,
            "error": str(raw["error"]),
        }

    return {
        "tool_name": tool_name,
        "result": raw,
        "success": True,
        "error": None,
    }


def execute_tool_with_retry(
    tool_name: str,
    tool_input: dict[str, Any],
    repo_id: str,
) -> dict[str, Any]:
    """
    Backward-compatible wrapper — returns bare tool result dict for legacy callers.

    Validates first; retries exactly once on any execution exception (Module 9a EC10).
  """
    try:
        if tool_name in _LEGACY_TOOL_MODELS:
            validated = _validate_legacy(tool_name, tool_input)
        else:
            validated = validate_call(tool_name, tool_input)
    except ToolValidationError as exc:
        return {"error": str(exc)}

    log = logger.bind(tool_name=tool_name, repo_id=repo_id)

    def _run() -> dict[str, Any]:
        return _dispatch_validated(validated, repo_id)

    try:
        result = _run()
        return result
    except Exception as exc:
        log.warning("tool_execution_failed_retrying", error=str(exc))
        time.sleep(1.0)
        try:
            return _run()
        except Exception as exc2:
            log.error("tool_execution_failed_final", error=str(exc2))
            return {"error": f"Tool execution failed after retry: {exc2}"}
