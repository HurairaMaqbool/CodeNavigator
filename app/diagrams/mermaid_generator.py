# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/diagrams/mermaid_generator.py
---------------------------------
Layer 6 — Graph Operations (Module #20).

Pure string generation: zero external dependencies, zero LLM cost.
Renders bounded subgraphs from app/graph/queries.py into valid Mermaid markdown.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# Characters that break Mermaid node labels when copied from code paths / identifiers.
_MERMAID_ESCAPE_MAP = {
    '"': "&quot;",
    "[": "&#91;",
    "]": "&#93;",
    "|": "&#124;",
    "(": "&#40;",
    ")": "&#41;",
    "\n": " ",
    "\r": " ",
}


def sanitize_node_label(label: str) -> str:
    """
    Escape display labels so code-derived identifiers cannot break Mermaid syntax.

    Handles: ``"`` ``[`` ``]`` ``|`` ``(`` ``)`` newlines — replaced with HTML
    entities (or a single space for line breaks).
    """
    out = str(label)
    for char, replacement in _MERMAID_ESCAPE_MAP.items():
        out = out.replace(char, replacement)
    return out


def sanitize(name: str, _seen_ids: dict[str, str] | None = None) -> str:
    """Stable Mermaid node ID, distinct from the human-readable label."""
    if _seen_ids is None:
        _seen_ids = {}

    if name in _seen_ids:
        return _seen_ids[name]

    if "/" in name or "\\" in name or ":" in name:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
        leaf = re.sub(r"[^a-zA-Z0-9_]", "_", name.split("/")[-1].split(":")[-1])[:24] or "node"
        safe_base = f"n_{leaf}_{digest}"
    else:
        safe_base = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    assigned = safe_base
    counter = 1
    used_ids = set(_seen_ids.values())
    while assigned in used_ids:
        assigned = f"{safe_base}_{counter}"
        counter += 1

    _seen_ids[name] = assigned
    return assigned


def _direction_header(direction: str) -> str:
    """Flowchart orientation keyword from traversal direction."""
    if direction == "downstream":
        return "graph LR"
    if direction == "upstream":
        return "graph BT"
    return "graph TD"


def _resolve_entry_point(subgraph: dict[str, Any], nodes_data: list[dict[str, Any]]) -> str:
    if subgraph.get("entry_point"):
        return str(subgraph["entry_point"])
    if len(nodes_data) == 1:
        return nodes_data[0]["id"]
    if nodes_data:
        return sorted(n["id"] for n in nodes_data)[0]
    return "entry"


def _no_connections_diagram(
    direction: str,
    entry_key: str,
    id_to_label: dict[str, str],
    seen_ids: dict[str, str],
) -> str:
    display_base = id_to_label.get(entry_key, entry_key)
    label = sanitize_node_label(f"{display_base}: no connections found")
    nid = sanitize(entry_key, seen_ids)
    return f'{_direction_header(direction)}\n    {nid}["{label}"]'


def _cycle_edge_set(cycles: list[list[str]], node_ids: set[str]) -> set[tuple[str, str]]:
    flagged: set[tuple[str, str]] = set()
    for cycle in cycles:
        if len(cycle) < 2:
            continue
        for i, src in enumerate(cycle):
            tgt = cycle[(i + 1) % len(cycle)]
            if src in node_ids and tgt in node_ids:
                flagged.add((src, tgt))
    return flagged


def generate_mermaid(
    subgraph: dict[str, Any],
    direction: str = "both",
    *,
    repo_id: str | None = None,
    max_nodes: int = 25,
) -> str:
    """
    Render a queries.py subgraph into Mermaid flowchart markdown.

    Input:  subgraph dict from get_subgraph() + direction string.
    Output: single valid Mermaid markdown string (never empty).
    """
    nodes_data = subgraph.get("nodes", [])
    edges_data = subgraph.get("edges", [])
    id_to_label = {}
    for n in nodes_data:
        path = n.get("path", "")
        name = n.get("name", n["id"])
        if path:
            id_to_label[n["id"]] = f"{path}:{name}"
        else:
            id_to_label[n["id"]] = name
    seen_ids: dict[str, str] = {}

    if subgraph.get("not_found") or not nodes_data:
        entry = _resolve_entry_point(subgraph, nodes_data)
        return _no_connections_diagram(direction, entry, {entry: entry}, seen_ids)

    if not edges_data:
        entry = _resolve_entry_point(subgraph, nodes_data)
        return _no_connections_diagram(direction, entry, id_to_label, seen_ids)

    header = _direction_header(direction)
    lines = [header]

    node_ids = {n["id"] for n in nodes_data}
    sorted_nodes = sorted(node_ids)
    kept_ids = set(sorted_nodes[:max_nodes])
    hidden_count = max(0, len(sorted_nodes) - max_nodes)

    cycle_edges: set[tuple[str, str]] = set()
    if repo_id:
        from app.graph.queries import get_cycle_info

        cycle_edges = _cycle_edge_set(get_cycle_info(repo_id), node_ids)

    cycle_nodes = {src for src, tgt in cycle_edges} | {tgt for src, tgt in cycle_edges}

    added_edges = 0
    declared: set[str] = set()

    for edge in edges_data:
        source = edge["source"]
        target = edge["target"]
        if source not in kept_ids or target not in kept_ids:
            continue
        src_id = sanitize(source, seen_ids)
        tgt_id = sanitize(target, seen_ids)
        src_label = sanitize_node_label(id_to_label.get(source, source))
        tgt_label = sanitize_node_label(id_to_label.get(target, target))
        is_cycle = (source, target) in cycle_edges
        if is_cycle:
            lines.append(f'    {src_id}["{src_label}"] -.->|cycle| {tgt_id}["{tgt_label}"]')
        else:
            lines.append(f'    {src_id}["{src_label}"] --> {tgt_id}["{tgt_label}"]')
        declared.update({source, target})
        added_edges += 1

    if added_edges == 0:
        entry = _resolve_entry_point(subgraph, nodes_data)
        return _no_connections_diagram(direction, entry, id_to_label, seen_ids)

    for node_key in kept_ids:
        if node_key not in declared:
            display = sanitize_node_label(id_to_label.get(node_key, node_key))
            nid = sanitize(node_key, seen_ids)
            suffix = " :::cycleNode" if node_key in cycle_nodes else ""
            lines.append(f'    {nid}["{display}"]{suffix}')

    if cycle_nodes:
        lines.append("    classDef cycleNode fill:#fff3cd,stroke:#d97706,stroke-width:2px")

    if hidden_count > 0:
        lines.append(f'    note["+{hidden_count} more dependencies not shown"]')

    return "\n".join(lines)


def graph_to_mermaid(
    subgraph: dict[str, Any],
    requested_depth: int,
    clamped_depth: int,
    max_nodes: int = 25,
    *,
    repo_id: str | None = None,
    direction: str = "both",
) -> dict[str, Any]:
    """Backward-compatible wrapper returning metadata + mermaid string for tests/tools."""
    mermaid = generate_mermaid(
        subgraph,
        direction=direction,
        repo_id=repo_id,
        max_nodes=max_nodes,
    )

    is_empty = "no connections found" in mermaid
    if is_empty:
        return {
            "mermaid": mermaid,
            "empty": True,
            "reason": "no_connections",
            "requested_depth": requested_depth,
            "clamped": requested_depth != clamped_depth,
        }

    return {
        "mermaid": mermaid,
        "empty": False,
        "requested_depth": requested_depth,
        "clamped": requested_depth != clamped_depth,
        "hidden_count": max(0, len(subgraph.get("nodes", [])) - max_nodes),
        "truncated_count": subgraph.get("truncated_count", 0),
        "hidden_neighbors": subgraph.get("hidden_neighbors", []),
        "direction": direction,
    }


def generate_diagram(
    repo_id: str,
    name: str,
    depth: int = 2,
    direction: str | None = None,
) -> dict[str, Any]:
    """Handoff wrapper used by agent tools — subgraph + mermaid metadata."""
    from app.config import settings
    from app.graph.queries import get_subgraph

    traversal = (direction or settings.DIAGRAM_DEFAULT_DIRECTION).strip().lower()
    if traversal not in ("upstream", "downstream", "both"):
        traversal = settings.DIAGRAM_DEFAULT_DIRECTION

    sub = get_subgraph(repo_id, name, direction=traversal, max_depth=depth)
    sub = {**sub, "entry_point": name}
    requested = sub.get("requested_depth", depth)
    clamped_depth = 3 if sub.get("clamped") else requested
    return graph_to_mermaid(
        sub,
        requested,
        clamped_depth,
        max_nodes=settings.GRAPH_SUBGRAPH_MAX_NODES,
        repo_id=repo_id,
        direction=traversal,
    )
