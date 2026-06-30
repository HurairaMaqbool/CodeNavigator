"""
app/agent/tools.py
------------------
Tool schemas, dispatch, and retry wrappers for the agent loop.

Responsibility boundary
-----------------------
Maps the Anthropic-style JSON schema declarations to the actual underlying implementation
functions. Translates inputs, catches errors, and enforces strict timeouts for external
tools.
It does NOT:
  - run the loop (see loop.py)
  - cache the results (see loop.py)
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.graph.queries import get_callees, get_callers
from app.observability.logging_config import logger

# Module 8 abstraction (for potential internal usage if needed)
from app.agent.llm_client import get_llm_client

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "search_code",
        "description": "Search the codebase semantically and via keyword. Returns ranked snippets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_callers",
        "description": "Find all functions that call a specific function.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_callees",
        "description": "Find all functions that a specific function calls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a specific file. Returns up to 800 lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "search_web_docs",
        "description": "Search the web for external documentation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_diagram",
        "description": "Generate a Mermaid call graph diagram outward from a function.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "depth": {"type": "integer", "default": 2}
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_subgraph",
        "description": "Traverse the call graph outward from a function up to 3 hops. Returns JSON structure of nodes and edges.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "depth": {"type": "integer", "default": 2}
            },
            "required": ["name"]
        }
    }
]

# ---------------------------------------------------------------------------
# Dispatch Logic
# ---------------------------------------------------------------------------

def _do_search_code(repo_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    from app.retrieval.hybrid_search import search_code
    is_groq = settings.LLM_PROVIDER.lower() == "groq"
    max_k = 5
    clamped_top_k = min(max(1, top_k), max_k)
    # Get a dummy LLM client or actual one for expansion
    llm = get_llm_client()
    max_pf = 1 if is_groq else 2
    results = search_code(query, repo_id, llm, clamped_top_k, max_per_file=max_pf)
    
    # Truncate each chunk to a safe character limit (e.g. 800 chars for Groq, 1200 for others)
    max_chunk_len = 800 if is_groq else 1200
    for r in results:
        if "chunk" in r and isinstance(r["chunk"], str) and len(r["chunk"]) > max_chunk_len:
            r["chunk"] = r["chunk"][:max_chunk_len] + "\n... [truncated, use read_file for full content] ..."
            
        # Clean up file paths in results metadata so the LLM sees clean relative paths
        meta = r.get("metadata", {})
        for path_key in ["file_path", "display_path", "normalized_path"]:
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
            
    return {"results": results}

def _do_get_callers(repo_id: str, name: str) -> dict[str, Any]:
    return {"results": get_callers(repo_id, name)}

def _do_get_callees(repo_id: str, name: str) -> dict[str, Any]:
    return {"results": get_callees(repo_id, name)}

def _do_read_file(repo_id: str, file_path: str) -> dict[str, Any]:
    from app.ingestion.file_filter import safe_decode
    from app.security.path_jail import PathJailError, resolve_jailed_path
    from pathlib import Path

    clone_root = Path(settings.REPOS_PATH) / repo_id / "clone"
    try:
        abs_path = resolve_jailed_path(clone_root, file_path)
    except PathJailError as exc:
        return {"error": str(exc)}

    if not abs_path.is_file():
        return {"error": f"File '{file_path}' not found or is not a file."}
        
    try:
        content_tuple = safe_decode(abs_path)
        text, error = content_tuple
        if error is not None:
            return {"error": f"Failed to read file: {error}"}
        content = text or ""
        lines = content.splitlines()
        
        # Output cap: ~150 lines for Groq (to fit in 6000 TPM limit), 800 lines for others
        limit = 150 if settings.LLM_PROVIDER.lower() == "groq" else 800
        if len(lines) > limit:
            truncated_lines = lines[:limit]
            rendered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(truncated_lines))
            return {
                "content": rendered,
                "truncated": True,
                "instruction": f"File exceeded {limit} lines and was truncated. Use search_code to target specific parts."
            }
        else:
            rendered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
            return {"content": rendered}
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

def _do_search_web_docs(repo_id: str, query: str) -> dict[str, Any]:
    # Hard 5-second timeout requirement
    timeout = settings.SEARCH_WEB_DOCS_TIMEOUT_S
    
    # Simple web search mock via duckduckgo html or basic wikipedia api
    # For robust demonstration, we use urllib to a public API with the timeout.
    import urllib.parse
    import urllib.request
    
    # We use a public Wikipedia API for a simple reliable stub, or just throw if offline
    # In a real system we'd use Tavily or similar.
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode())
            snippets = [item["snippet"] for item in data.get("query", {}).get("search", [])[:3]]
            return {"results": snippets}
    except Exception as e:
        logger.warning("web_search_failed", query=query, error=str(e))
        return {
            "error": f"web search timed out after {timeout}s" if isinstance(e, TimeoutError) else f"web search failed: {e}",
            "instruction": "Do not retry this exact search. Proceed using existing codebase knowledge, or inform the user you could not reach external documentation for this query."
        }

def _do_generate_diagram(repo_id: str, name: str, depth: int = 2) -> dict[str, Any]:
    try:
        from app.diagrams.generator import generate_diagram
        return {"mermaid": generate_diagram(repo_id, name, depth)}
    except ImportError:
        from app.graph.queries import get_subgraph
        sub = get_subgraph(repo_id, name, depth)
        return {"mermaid": f"graph TD;\n  {name}-->Stub;\n", "clamped": sub.get("clamped", False)}

def _do_get_subgraph(repo_id: str, name: str, depth: int = 2) -> dict[str, Any]:
    from app.graph.queries import get_subgraph
    return get_subgraph(repo_id, name, depth)

# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def execute_tool_with_retry(tool_name: str, tool_input: dict[str, Any], repo_id: str) -> dict[str, Any]:
    """
    Executes a tool by name, catching exceptions and retrying exactly once
    with backoff for retryable errors.
    """
    log = logger.bind(tool_name=tool_name, repo_id=repo_id)
    
    def _run():
        if tool_name == "search_code":
            return _do_search_code(repo_id, tool_input.get("query", ""), tool_input.get("top_k", 5))
        elif tool_name == "get_callers":
            return _do_get_callers(repo_id, tool_input.get("name", ""))
        elif tool_name == "get_callees":
            return _do_get_callees(repo_id, tool_input.get("name", ""))
        elif tool_name == "read_file":
            return _do_read_file(repo_id, tool_input.get("file_path", ""))
        elif tool_name == "search_web_docs":
            return _do_search_web_docs(repo_id, tool_input.get("query", ""))
        elif tool_name == "generate_diagram":
            return _do_generate_diagram(repo_id, tool_input.get("name", ""), tool_input.get("depth", 2))
        elif tool_name == "get_subgraph":
            return _do_get_subgraph(repo_id, tool_input.get("name", ""), tool_input.get("depth", 2))
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    try:
        return _run()
    except Exception as e:
        log.warning("tool_execution_failed_retrying", error=str(e))
        # Wait 1s backoff
        time.sleep(1.0)
        try:
            return _run()
        except Exception as e2:
            log.error("tool_execution_failed_final", error=str(e2))
            return {"error": f"Tool execution failed after retry: {e2}"}
