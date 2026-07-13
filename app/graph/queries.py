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
# Global Graph Cache (short TTL — avoids disk reload within a request burst)
# ---------------------------------------------------------------------------
import time

_GRAPH_CACHE: dict[str, tuple[float, nx.DiGraph]] = {}
_GRAPH_CACHE_TTL_S = 60.0


def _get_graph(repo_id: str) -> nx.DiGraph | None:
    """Return the DiGraph for *repo_id*, loading via builder.get_graph() when needed."""
    now = time.monotonic()
    cached = _GRAPH_CACHE.get(repo_id)
    if cached is not None:
        loaded_at, graph = cached
        if now - loaded_at < _GRAPH_CACHE_TTL_S:
            return graph

    from app.graph.builder import get_graph

    graph = get_graph(repo_id)
    if graph is not None:
        _GRAPH_CACHE[repo_id] = (now, graph)
    return graph


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


def _neighbor_rank_score(graph: nx.DiGraph, node_id: str, edge_data: dict[str, Any]) -> float:
    """Rank neighbors by call frequency and graph centrality (reuse onboarding signal)."""
    call_count = float(edge_data.get("call_count", 1) or 1)
    in_deg = float(graph.in_degree(node_id))
    out_deg = float(graph.out_degree(node_id))
    return call_count * 10.0 + in_deg + out_deg


def _collect_capped_neighbors(
    graph: nx.DiGraph,
    u: str,
    direction: str,
    max_fanout: int,
) -> tuple[list[tuple[str, str, dict[str, Any]]], list[dict[str, Any]]]:
    """
    Return kept edges (source, target, data) and hidden neighbor metadata.

    Caps fan-out per node so hub symbols do not explode the subgraph.
    """
    candidates: list[tuple[str, str, dict[str, Any], str, float]] = []

    if direction in ("downstream", "both"):
        for v in graph.successors(u):
            edge_data = graph.edges[u, v]
            score = _neighbor_rank_score(graph, v, edge_data)
            candidates.append((u, v, edge_data, "callee", score))

    if direction in ("upstream", "both"):
        for w in graph.predecessors(u):
            edge_data = graph.edges[w, u]
            score = _neighbor_rank_score(graph, w, edge_data)
            candidates.append((w, u, edge_data, "caller", score))

    candidates.sort(key=lambda item: item[4], reverse=True)
    kept = candidates[:max_fanout]
    hidden_raw = candidates[max_fanout:]

    edges_out = [(src, tgt, data) for src, tgt, data, _, _ in kept]
    parent_name = graph.nodes[u].get("name", u)
    hidden_neighbors: list[dict[str, Any]] = []
    for src, tgt, _, direction_kind, _ in hidden_raw:
        neighbor_id = tgt if direction_kind == "callee" else src
        hidden_neighbors.append(
            {
                "parent_id": u,
                "parent_name": parent_name,
                "direction": direction_kind,
                "id": neighbor_id,
                "name": graph.nodes[neighbor_id].get("name", neighbor_id),
                "path": graph.nodes[neighbor_id].get("path", ""),
            }
        )
    return edges_out, hidden_neighbors


def get_subgraph(
    repo_id: str,
    entry_point: str,
    direction: str = "both",
    max_depth: int = 3,
    *,
    depth: int | None = None,
    max_fanout: int | None = None,
) -> dict[str, Any]:
    """
    Traverses outward from entry_point up to max_depth hops.

    Parameters
    ----------
    repo_id: str
        The repository ID.
    entry_point: str
        The starting node ID (or name).
    direction: str
        One of "upstream", "downstream", or "both".
    max_depth: int
        Maximum BFS hops to traverse.
    depth: int | None
        Legacy alias for ``max_depth`` (accepted by older callers/tests).

    Forward Interface Contract:
    --------------------------
    Returns:
        dict: {
            "nodes": list[dict[str, Any]],  # each node has id, path, name, type
            "edges": list[dict[str, Any]],  # each edge has source, target, type, call_count
            "requested_depth": int,
            "clamped": bool
        }
    """
    # Dynamic parameter type shifting for backward compatibility
    if isinstance(direction, int):
        max_depth = direction
        direction = "both"
    if depth is not None:
        max_depth = depth

    fanout_cap = max_fanout if max_fanout is not None else settings.GRAPH_SUBGRAPH_MAX_FANOUT
    direction = direction if direction in ("upstream", "downstream", "both") else "both"

    original_depth = max_depth
    clamped = (max_depth > 3)
    clamped_depth = min(max(1, max_depth), 3)

    graph = _get_graph(repo_id)
    if not graph:
        return {
            "nodes": [],
            "edges": [],
            "requested_depth": original_depth,
            "clamped": clamped,
            "hidden_neighbors": [],
            "truncated_count": 0,
        }

    # Resolve entry_point to node IDs
    start_nodes = []
    if entry_point in graph:
        start_nodes = [entry_point]
    else:
        start_nodes = _find_matching_nodes(graph, entry_point)

    if not start_nodes:
        return {
            "nodes": [],
            "edges": [],
            "requested_depth": original_depth,
            "clamped": clamped,
            "not_found": True,
            "hidden_neighbors": [],
            "truncated_count": 0,
        }

    # BFS traversal with per-node fan-out cap
    visited_nodes: set[str] = set(start_nodes)
    current_layer: set[str] = set(start_nodes)
    edges: list[dict[str, Any]] = []
    hidden_neighbors: list[dict[str, Any]] = []

    for _ in range(clamped_depth):
        next_layer: set[str] = set()
        for u in current_layer:
            kept_edges, hidden = _collect_capped_neighbors(
                graph, u, direction, fanout_cap,
            )
            hidden_neighbors.extend(hidden)
            for src, tgt, edge_data in kept_edges:
                edges.append({
                    "source": src,
                    "target": tgt,
                    "type": edge_data.get("type", "unknown"),
                    "call_count": edge_data.get("call_count", 1),
                })
                neighbor = tgt if src == u else src
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    next_layer.add(neighbor)

        current_layer = next_layer
        if not current_layer:
            break

    # Dedup edges
    unique_edges = {f"{e['source']}->{e['target']}": e for e in edges}.values()

    seen_hidden: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in hidden_neighbors:
        dedupe_key = (entry["parent_id"], entry["id"], entry["direction"])
        if dedupe_key not in seen_hidden:
            seen_hidden[dedupe_key] = entry
    hidden_neighbors = list(seen_hidden.values())

    nodes_out = [
        {
            "id": n,
            "name": graph.nodes[n].get("name", n),
            "path": graph.nodes[n].get("path", ""),
            "type": graph.nodes[n].get("type", ""),
            "start_line": graph.nodes[n].get("start_line"),
            "end_line": graph.nodes[n].get("end_line"),
        }
        for n in visited_nodes
    ]

    return {
        "nodes": nodes_out,
        "edges": list(unique_edges),
        "requested_depth": original_depth,
        "clamped": clamped,
        "hidden_neighbors": hidden_neighbors,
        "truncated_count": len(hidden_neighbors),
    }


def get_dependencies(repo_id: str, node_id: str) -> list[str]:
    """
    Return direct dependencies (outgoing edges) of a node.
    Uses networkx's successors utility.
    """
    graph = _get_graph(repo_id)
    if not graph:
        return []
        
    start_nodes = [node_id] if node_id in graph else _find_matching_nodes(graph, node_id)
    if not start_nodes:
        return []
        
    deps = set()
    for node in start_nodes:
        deps.update(graph.successors(node))
    return list(deps)


def get_dependents(repo_id: str, node_id: str) -> list[str]:
    """
    Return direct dependents (incoming edges) of a node.
    Uses networkx's predecessors utility.
    """
    graph = _get_graph(repo_id)
    if not graph:
        return []
        
    start_nodes = [node_id] if node_id in graph else _find_matching_nodes(graph, node_id)
    if not start_nodes:
        return []
        
    deps = set()
    for node in start_nodes:
        deps.update(graph.predecessors(node))
    return list(deps)


def get_cycle_info(repo_id: str) -> list[list[str]]:
    """
    Return the pre-computed cycle list for the repository.
    Surfaces builder.py's precomputed cycle list without recomputing it.
    """
    path = _graph_path_for(repo_id)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload["metadata"].get("cycles", [])
    except Exception as exc:
        logger.warning("failed_to_get_cycle_info", repo_id=repo_id, error=str(exc))
        return []


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
