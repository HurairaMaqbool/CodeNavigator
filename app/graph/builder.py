# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/graph/builder.py
--------------------
Call graph construction and persistence.

Responsibility boundary
-----------------------
This module constructs a NetworkX DiGraph from parsed functions and persists it
safely to disk.
It does NOT:
  - parse the code itself (Module 5),
  - execute queries against the graph (see queries.py),
  - draw diagrams (Module 11).

Edge Confidence Typing
----------------------
Edges carry an honest `type`: "static", "semi_static", or "heuristic".
We do not use a fake numeric confidence score (e.g. "87%"). A pseudo-precise
number implies statistical calibration that static analysis across dynamically
typed languages lacks. An honest category allows downstream UI (Module 14) to
signal actual knowns vs guesses to the user.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import networkx as nx  # type: ignore[import]

from app.config import settings
from app.observability.logging_config import logger
from app.parsing.tree_sitter_parser import ParsedFile

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _graph_path_for(repo_id: str) -> Path:
    """Return the absolute path to the graph.json for *repo_id*."""
    return Path(settings.GRAPH_STORE_PATH) / repo_id / "graph.json"


# ---------------------------------------------------------------------------
# Build Logic
# ---------------------------------------------------------------------------

def build_graph(
    repo_id: str,
    parsed_files: list[ParsedFile],
) -> None:
    """
    Build a call graph from the parsed AST data and persist it atomically.

    Enforces MAX_GRAPH_NODES. If exceeded, drops excess nodes deterministically
    (by file-walk order) and marks the graph as truncated.
    Handles dangling edges cleanly: edges pointing to non-existent nodes are omitted.

    Parameters
    ----------
    repo_id:
        The repository identifier.
    parsed_files:
        The parsed output from Module 5.
    """
    log = logger.bind(repo_id=repo_id)
    graph = nx.DiGraph()

    max_nodes = settings.MAX_GRAPH_NODES
    truncated = False
    node_count = 0

    # 1. First pass: Collect all valid function/method nodes.
    #    We key them by `{normalized_path}:{name}` to ensure uniqueness.
    #    This deterministic file-walk order guarantees consistent truncation if we hit the limit.
    known_nodes: set[str] = set()

    for p_file in parsed_files:
        if node_count >= max_nodes:
            truncated = True
            break

        path = getattr(p_file, 'normalized_path', None) or p_file.file_path.lower()

        # Top-level functions
        for f in p_file.functions:
            if node_count >= max_nodes:
                truncated = True
                break
            node_id = f"{path}:{f.name}"
            graph.add_node(node_id, path=path, name=f.name, type="function")
            known_nodes.add(node_id)
            node_count += 1

        # Class methods
        for c in p_file.classes:
            for m in c.methods:
                if node_count >= max_nodes:
                    truncated = True
                    break
                node_id = f"{path}:{c.name}.{m.name}"
                graph.add_node(node_id, path=path, name=f"{c.name}.{m.name}", type="method", class_name=c.name)
                known_nodes.add(node_id)
                node_count += 1

    if truncated:
        log.warning("graph_truncated", max_nodes=max_nodes)

    # 2. Second pass: Wire up the edges.
    #    We must only add edges if BOTH the caller and the callee exist in `known_nodes`.
    #    This natively prevents dangling edges when files are deleted incrementally, or if truncation dropped a node.

    # Build a lookup table from simple name -> list of node_ids
    # This allows us to resolve cross-file calls heuristically.
    name_to_nodes: dict[str, list[str]] = {}
    for node_id in known_nodes:
        # node_id is path:name
        _, _, name = node_id.rpartition(":")
        name_to_nodes.setdefault(name, []).append(node_id)

    edge_count = 0
    for p_file in parsed_files:
        path = getattr(p_file, 'normalized_path', None) or p_file.file_path.lower()

        # Helper to process calls for a given function/method node
        def _process_calls(caller_id: str, calls: list[str]) -> None:
            nonlocal edge_count
            if caller_id not in known_nodes:
                return

            for call in calls:
                targets = name_to_nodes.get(call, [])
                if not targets:
                    # Called function is outside our parsed codebase (e.g., standard library, pip package, or unparsed file)
                    continue

                if len(targets) == 1:
                    callee_id = targets[0]
                    # Same file -> static. Cross file -> semi_static (we didn't trace the exact import path, but it's unambiguous).
                    edge_type = "static" if callee_id.startswith(f"{path}:") else "semi_static"
                    resolution = "exact_match"
                else:
                    # Multiple targets share this name. Heuristic resolution.
                    # If one is in the SAME file, we statically assume that's the one.
                    local_target = f"{path}:{call}"
                    if local_target in targets:
                        callee_id = local_target
                        edge_type = "static"
                        resolution = "local_priority"
                    else:
                        # Otherwise, we just pick the first one and flag it heuristic.
                        # (A more advanced implementation would look at parsed imports).
                        callee_id = targets[0]
                        edge_type = "heuristic"
                        resolution = "name_collision_fallback"

                if callee_id in known_nodes:
                    # We only add the edge if the callee actually exists in the graph.
                    # This prevents dangling edges if the callee was dropped due to truncation.
                    if graph.has_edge(caller_id, callee_id):
                        graph[caller_id][callee_id]["call_count"] += 1
                    else:
                        graph.add_edge(
                            caller_id, callee_id,
                            call_count=1,
                            type=edge_type,
                            resolution_method=resolution
                        )
                        edge_count += 1

        for f in p_file.functions:
            _process_calls(f"{path}:{f.name}", f.calls)

        for c in p_file.classes:
            for m in c.methods:
                _process_calls(f"{path}:{c.name}.{m.name}", m.calls)

    log.info("graph_built", nodes=graph.number_of_nodes(), edges=graph.number_of_edges(), truncated=truncated)

    has_circular_dependencies = False
    if graph.number_of_nodes() > 0:
        try:
            has_circular_dependencies = not nx.is_directed_acyclic_graph(graph)
        except Exception:
            has_circular_dependencies = False

    # 3. Serialize and persist atomically.
    #    We write to a `.tmp` file and use os.replace() to overwrite the final target.
    #    This ensures that if the process crashes mid-write, the old graph.json remains
    #    intact and uncorrupted.
    data = nx.node_link_data(graph)
    payload = {
        "metadata": {
            "graph_truncated": truncated,
            "repo_id": repo_id,
            "has_circular_dependencies": has_circular_dependencies,
        },
        "graph": data
    }

    final_path = _graph_path_for(repo_id)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_suffix(".json.tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)

    # Atomic replace
    os.replace(tmp_path, final_path)
    log.debug("graph_persisted_atomically", path=str(final_path))
