# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/graph/queries.py
--------------------
Defensive lookup API for the call graph.

Responsibility boundary
-----------------------
This module loads the persisted graph from disk and exposes clean, defensive
functions to query it.
It does NOT:
  - generate Mermaid diagrams (Module 11),
  - expose LLM tool wrappers (Module 9).
"""
from __future__ import annotations

import json
from threading import Thread
from typing import Any

import networkx as nx  # type: ignore[import]

from app.config import settings
from app.graph.builder import _graph_path_for
from app.observability.logging_config import logger

# ---------------------------------------------------------------------------
# Global Graph Cache (Lazy Load)
# ---------------------------------------------------------------------------
# We hold graphs in memory keyed by repo_id to avoid parsing JSON on every query.
_GRAPH_CACHE: dict[str, nx.DiGraph] = {}


def _get_graph(repo_id: str) -> nx.DiGraph | None:
    """Return the DiGraph for *repo_id*, loading it if necessary."""
    if repo_id in _GRAPH_CACHE:
        return _GRAPH_CACHE[repo_id]

    path = _graph_path_for(repo_id)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        graph = nx.node_link_graph(payload["graph"])
        _GRAPH_CACHE[repo_id] = graph
        return graph
    except Exception as exc:
        logger.error("failed_to_load_graph", repo_id=repo_id, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Public Query API
# ---------------------------------------------------------------------------

def _find_matching_nodes(graph: nx.DiGraph, name: str) -> list[str]:
    """
    Find nodes matching 'name' using fallback strategies:
    1. Exact match (by node ID or 'name' attribute).
    2. Class name match (all methods on a class).
    3. Ends with '.{searched_name}' (by node ID or 'name' attribute).
    4. Contains '{searched_name}' (case-insensitive, by node ID or 'name' attribute).
    """
    # 1. Exact match
    matches = [n for n, attr in graph.nodes(data=True) if attr.get("name") == name or n == name]
    if matches:
        return matches

    # 2. Class name — e.g. "PreparedRequest" -> PreparedRequest.prepare, etc.
    class_matches = [
        n for n, attr in graph.nodes(data=True)
        if attr.get("class_name") == name
        or (attr.get("name") or "").startswith(f"{name}.")
        or n.endswith(f":{name}.")  # rare edge case
    ]
    if class_matches:
        return class_matches
    prefix = f"{name}."
    prefix_matches = [
        n for n, attr in graph.nodes(data=True)
        if (attr.get("name") or "").startswith(prefix) or n.split(":")[-1].startswith(prefix)
    ]
    if prefix_matches:
        return prefix_matches

    # 3. Ends with '.{searched_name}'
    suffix = f".{name}"
    matches = [
        n for n, attr in graph.nodes(data=True)
        if (attr.get("name") and attr.get("name").endswith(suffix)) or n.endswith(suffix)
    ]
    if matches:
        return matches

    # 3. Contains '{searched_name}' case-insensitive
    lower_name = name.lower()
    matches = [
        n for n, attr in graph.nodes(data=True)
        if (attr.get("name") and lower_name in attr.get("name").lower()) or lower_name in n.lower()
    ]
    return matches


def get_callers(repo_id: str, name: str) -> list[dict[str, Any]]:
    """
    Return all functions that call *name*.
    
    Defensive: If the graph is missing or *name* doesn't exist, returns [].
    Never raises KeyError.
    """
    graph = _get_graph(repo_id)
    if not graph:
        return []

    matches = _find_matching_nodes(graph, name)
    if not matches:
        return []

    callers = []
    seen_callers = set()
    for target_id in matches:
        # in_edges gives us (u, v) where u calls v
        for u, v, data in graph.in_edges(target_id, data=True):
            caller_node = graph.nodes[u]
            caller_name = caller_node.get("name", u)
            caller_path = caller_node.get("path")
            key = (caller_name, caller_path)
            if key not in seen_callers:
                seen_callers.add(key)
                callers.append({
                    "caller": caller_name,
                    "path": caller_path,
                    "call_count": data.get("call_count", 1),
                    "edge_type": data.get("type", "unknown")
                })

    return callers


def get_callees(repo_id: str, name: str) -> list[dict[str, Any]]:
    """
    Return all functions that *name* calls.
    
    Defensive: Returns [] if missing. Never raises KeyError.
    """
    graph = _get_graph(repo_id)
    if not graph:
        return []

    matches = _find_matching_nodes(graph, name)
    if not matches:
        return []

    callees = []
    seen_callees = set()
    for target_id in matches:
        # out_edges gives us (u, v) where u calls v
        for u, v, data in graph.out_edges(target_id, data=True):
            callee_node = graph.nodes[v]
            callee_name = callee_node.get("name", v)
            callee_path = callee_node.get("path")
            key = (callee_name, callee_path)
            if key not in seen_callees:
                seen_callees.add(key)
                callees.append({
                    "callee": callee_name,
                    "path": callee_path,
                    "call_count": data.get("call_count", 1),
                    "edge_type": data.get("type", "unknown")
                })

    return callees


def get_subgraph(repo_id: str, name: str, depth: int = 2) -> dict[str, Any]:
    """
    Traverses outward from *name* up to *depth* hops.
    
    Server-side clamp: Max depth is strictly limited to 3.
    """
    original_depth = depth
    depth = min(depth, 3)
    clamped = (original_depth > 3)

    graph = _get_graph(repo_id)
    if not graph:
        return {"nodes": [], "edges": [], "requested_depth": original_depth, "clamped": clamped}

    matches = _find_matching_nodes(graph, name)
    if not matches:
        return {"nodes": [], "edges": [], "requested_depth": original_depth, "clamped": clamped, "not_found": True}

    # We use a BFS out to `depth` hops starting from all matches
    visited_nodes: set[str] = set(matches)
    current_layer: set[str] = set(matches)
    edges: list[dict[str, Any]] = []

    for _ in range(depth):
        next_layer: set[str] = set()
        for u in current_layer:
            # Outgoing
            for _, v, data in graph.out_edges(u, data=True):
                if v not in visited_nodes:
                    visited_nodes.add(v)
                    next_layer.add(v)
                edges.append({"source": graph.nodes[u].get("name", u), "target": graph.nodes[v].get("name", v), "data": data})
            # Incoming
            for w, _, data in graph.in_edges(u, data=True):
                if w not in visited_nodes:
                    visited_nodes.add(w)
                    next_layer.add(w)
                edges.append({"source": graph.nodes[w].get("name", w), "target": graph.nodes[u].get("name", u), "data": data})
        current_layer = next_layer
        if not current_layer:
            break

    # Dedup edges since u->v could be hit from both sides
    unique_edges = {f"{e['source']}->{e['target']}": e for e in edges}.values()

    nodes_out = [{"id": n, "name": graph.nodes[n].get("name", n), "path": graph.nodes[n].get("path")} for n in visited_nodes]

    return {
        "nodes": nodes_out,
        "edges": list(unique_edges),
        "requested_depth": original_depth,
        "clamped": clamped
    }


# ---------------------------------------------------------------------------
# Cycle Detection (Hard Timeout)
# ---------------------------------------------------------------------------

class TimeoutException(Exception):
    pass


def detect_cycles(repo_id: str) -> bool | None:
    """
    Detect if the graph contains any directed cycles.

    Uses NetworkX `is_directed_acyclic_graph` (O(V+E)) with a wall-clock cap.
    Returns True if a cycle exists, False if acyclic, None if the check timed out.
    """
    graph = _get_graph(repo_id)
    if not graph or graph.number_of_nodes() == 0:
        return False

    timeout_s = settings.CYCLE_DETECTION_TIMEOUT_S
    log = logger.bind(repo_id=repo_id)
    result: list[bool | None] = [None]

    def _run_check() -> None:
        try:
            result[0] = not nx.is_directed_acyclic_graph(graph)
        except Exception:
            result[0] = None

    thread = Thread(target=_run_check, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)

    if thread.is_alive():
        log.warning("cycle_detection_timeout", limit_s=timeout_s)
        return None

    return result[0]
