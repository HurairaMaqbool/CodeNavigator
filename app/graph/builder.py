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
    definitions: list[ParsedFile] | None = None,
    parsed_files: list[ParsedFile] | None = None,
) -> nx.DiGraph:
    """
    Build a call graph from the parsed AST data and persist it atomically.

    Enforces MAX_GRAPH_NODES. If exceeded, drops excess nodes deterministically
    (by file-walk order) and marks the graph as truncated.
    Handles dangling edges cleanly: edges pointing to non-existent nodes are omitted.

    Parameters
    ----------
    repo_id:
        The repository identifier.
    definitions:
        The parsed files list from tree_sitter_parser.py.
    parsed_files:
        Alias for definitions parameter, kept for backwards compatibility.

    Returns
    -------
    nx.DiGraph
        The constructed NetworkX directed graph object.
    """
    log = logger.bind(repo_id=repo_id)
    graph = nx.DiGraph()

    files = definitions if definitions is not None else parsed_files
    if files is None:
        files = []

    max_nodes = settings.MAX_GRAPH_NODES
    truncated = False
    node_count = 0

    # 1. First pass: Collect all valid function/method nodes.
    #    We key them by `{normalized_path}:{name}` to ensure uniqueness.
    #    This deterministic file-walk order guarantees consistent truncation if we hit the limit.
    known_nodes: set[str] = set()

    for p_file in files:
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
    for p_file in files:
        path = getattr(p_file, 'normalized_path', None) or p_file.file_path.lower()

        # Helper to process calls for a given function/method node
        def _process_calls(caller_id: str, calls: list[str]) -> None:
            nonlocal edge_count
            if caller_id not in known_nodes:
                return

            for call in calls:
                targets = name_to_nodes.get(call, [])
                if not targets:
                    # Called function is outside our parsed codebase
                    continue

                if len(targets) == 1:
                    callee_id = targets[0]
                    edge_type = "static" if callee_id.startswith(f"{path}:") else "semi_static"
                    resolution = "exact_match"
                else:
                    local_target = f"{path}:{call}"
                    if local_target in targets:
                        callee_id = local_target
                        edge_type = "static"
                        resolution = "local_priority"
                    else:
                        callee_id = targets[0]
                        edge_type = "heuristic"
                        resolution = "name_collision_fallback"

                if callee_id in known_nodes:
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

    # 3. Detect Cycles
    cycles = detect_cycles(graph)
    has_circular_dependencies = len(cycles) > 0

    # 4. Serialize and persist atomically.
    data = nx.node_link_data(graph)
    payload = {
        "metadata": {
            "graph_truncated": truncated,
            "repo_id": repo_id,
            "has_circular_dependencies": has_circular_dependencies,
            "cycles": cycles,
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

    # Write progress checkpoint to metadata_store
    from app.ingestion.metadata_store import metadata_store, Stage
    try:
        metadata_store.update(
            repo_id,
            Stage.INDEXING,
            has_circular_dependencies=has_circular_dependencies,
            progress="Graph construction complete"
        )
    except Exception as exc:
        logger.warning("failed_to_write_graph_metadata_checkpoint", error=str(exc))

    return graph


def detect_cycles(graph: nx.DiGraph) -> list[list[str]]:
    """
    Find circular import/call chains in the graph.
    Uses networkx.simple_cycles which is a DFS-based cycle search algorithm.
    """
    if graph.number_of_nodes() == 0:
        return []
    try:
        return list(nx.simple_cycles(graph))
    except Exception as exc:
        logger.warning("cycle_detection_failed", error=str(exc))
        return []


def get_graph(repo_id: str) -> nx.DiGraph | None:
    """
    Load and return the persisted directed graph for repo_id.
    """
    path = _graph_path_for(repo_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return nx.node_link_graph(payload["graph"])
    except Exception as exc:
        logger.warning("failed_to_load_graph", repo_id=repo_id, error=str(exc))
        return None
