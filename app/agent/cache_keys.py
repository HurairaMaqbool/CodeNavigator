"""
app/agent/cache_keys.py
-----------------------
Cache key normalization for tool calls.
"""
import hashlib
import json
from typing import Any

from app.agent.tools import TOOL_DEFINITIONS

def _get_schema_defaults(tool_name: str) -> dict[str, Any]:
    for t in TOOL_DEFINITIONS:
        if t["name"] == tool_name:
            props = t.get("input_schema", {}).get("properties", {})
            return {k: v["default"] for k, v in props.items() if "default" in v}
    return {}

def normalize_cache_key(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Produce a canonical cache key for a tool call.
    
    1. Apply schema defaults (so `{"depth": 2}` and `{}` match if 2 is default).
    2. Produce recursively key-sorted canonical JSON.
    3. Hash it.
    
    Why not frozenset(dict.items())?
    Because frozenset breaks if values are nested dicts/lists, which are unhashable.
    Canonical JSON handles arbitrarily nested structures safely.
    """
    defaults = _get_schema_defaults(tool_name)
    
    # Create a merged dict (tool_input overrides defaults)
    merged = {**defaults}
    for k, v in tool_input.items():
        if v is not None:
            merged[k] = v

    # Canonical json string
    canonical = json.dumps(merged, sort_keys=True, separators=(",", ":"))
    
    hashed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{tool_name}:{hashed}"
