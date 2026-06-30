"""
app/diagrams/mermaid_generator.py
---------------------------------
Diagram generation layer.

Responsibility boundary
-----------------------
Pure function that converts graph data from Module 7 into valid Mermaid syntax.
It does NOT:
  - execute queries against the graph itself
  - handle HTTP routing or agent loop execution
"""
from __future__ import annotations

import re
from typing import Any


def sanitize(name: str, _seen_ids: dict[str, str] | None = None) -> str:
    """
    Sanitize a function name into a safe Mermaid node ID.
    Mermaid node IDs should be strictly alphanumeric/underscores.
    
    If _seen_ids is provided, it handles collision resolution by appending
    a numeric suffix to disambiguate identical sanitized strings.
    """
    if _seen_ids is None:
        _seen_ids = {}
        
    safe_base = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    
    # If this exact name was already sanitized, return its assigned ID
    if name in _seen_ids:
        return _seen_ids[name]
        
    # Check if the generated safe_base is already used by a DIFFERENT name
    assigned = safe_base
    counter = 1
    # _seen_ids.values() check is linear, but node count is max 25, so O(N) is trivial.
    used_ids = set(_seen_ids.values())
    while assigned in used_ids:
        assigned = f"{safe_base}_{counter}"
        counter += 1
        
    _seen_ids[name] = assigned
    return assigned


def graph_to_mermaid(subgraph: dict[str, Any], requested_depth: int, clamped_depth: int, max_nodes: int = 25) -> dict[str, Any]:
    """
    Convert a subgraph into valid Mermaid diagram syntax.
    
    Why a node cap?
    ---------------
    A central, widely-used function can easily have 100+ nodes in its call graph.
    Rendering all of them produces an unreadable diagram. The cap plus a visible
    "+N more dependencies not shown" note keeps the diagram legible while staying honest.
    
    `clamped` (depth) and `hidden_count` (node truncation) are distinct signals.
    """
    # Extract nodes and edges from the Module 7 dict format
    nodes_data = subgraph.get("nodes", [])
    edges_data = subgraph.get("edges", [])
    
    if not nodes_data or subgraph.get("not_found"):
        return {
            "mermaid": None,
            "empty": True,
            "reason": "no_connections",
            "requested_depth": requested_depth,
            "clamped": requested_depth != clamped_depth
        }

    lines = ["graph TD"]
    
    node_names = [n["id"] for n in nodes_data]
    node_names = sorted(node_names)
    
    kept_ids = set(node_names[:max_nodes])
    kept_names = {n.get("name", n["id"]) for n in nodes_data if n["id"] in kept_ids}
    hidden_count = max(0, len(node_names) - max_nodes)
    
    seen_ids: dict[str, str] = {}
    
    if not edges_data:
        for n in nodes_data:
            if n["id"] not in kept_ids:
                continue
            display = n.get("name", n["id"])
            safe_id = sanitize(display, seen_ids)
            lines.append(f'    {safe_id}["{display}"]')
        if hidden_count > 0:
            lines.append(f'    note["+{hidden_count} more dependencies not shown"]')
        return {
            "mermaid": "\n".join(lines),
            "empty": False,
            "requested_depth": requested_depth,
            "clamped": requested_depth != clamped_depth,
            "hidden_count": hidden_count,
        }

    added_edges = 0
    for edge in edges_data:
        source = edge["source"]
        target = edge["target"]
        
        # In get_subgraph, edges refer to node names or IDs
        # We need to map them to the full names
        
        if (source in kept_ids or source in kept_names) and (target in kept_ids or target in kept_names):
            source_id = sanitize(source, seen_ids)
            target_id = sanitize(target, seen_ids)
            
            # The brackets define the human-readable label
            lines.append(f'    {source_id}["{source}"] --> {target_id}["{target}"]')
            added_edges += 1
            
    # Handle edgeless subgraphs (e.g. leaf function requested with depth=2)
    # If no edges were added, we must explicitly declare the kept nodes so they render.
    if added_edges == 0:
        for node in node_names:
            if node in kept_ids:
                nid = sanitize(node, seen_ids)
                lines.append(f'    {nid}["{node}"]')
            
    if hidden_count > 0:
        lines.append(f'    note["+{hidden_count} more dependencies not shown"]')
        
    return {
        "mermaid": "\n".join(lines),
        "requested_depth": requested_depth,
        "clamped": requested_depth != clamped_depth
    }

def generate_diagram(repo_id: str, name: str, depth: int = 2) -> dict[str, Any]:
    """
    Handoff wrapper used by Module 9a tools.py.
    Calls Module 7's get_subgraph and passes the result to graph_to_mermaid.
    """
    from app.graph.queries import get_subgraph
    
    sub = get_subgraph(repo_id, name, depth)
    
    requested = sub.get("requested_depth", depth)
    # If clamped is True, Module 7 clamped it to 3.
    clamped_depth = 3 if sub.get("clamped") else requested
    
    return graph_to_mermaid(sub, requested, clamped_depth, max_nodes=25)
