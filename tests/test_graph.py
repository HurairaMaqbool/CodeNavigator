# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_graph.py
-------------------
Unit tests for Module 7 (Call Graph Builder & Queries).

Run with:
    python -m unittest tests/test_graph.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Bootstrap: mock structlog
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

from app.config import settings
from app.graph.builder import build_graph, _graph_path_for
from app.graph.queries import (
    _GRAPH_CACHE,
    detect_cycles,
    get_callees,
    get_callers,
    get_subgraph,
)
from app.parsing.tree_sitter_parser import ParsedFile, ParsedFunction


class TestGraphBuilderAndQueries(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        settings.GRAPH_STORE_PATH = self.td.name
        self.repo_id = "repo_graph_123"
        _GRAPH_CACHE.clear()

    def tearDown(self):
        self.td.cleanup()

    def test_build_and_query_basic(self):
        # A calls B
        f_b = ParsedFunction("b", 10, 15, calls=[])
        f_a = ParsedFunction("a", 1, 5, calls=["b"])
        pfile = ParsedFile("src/main.py", "python", functions=[f_a, f_b], normalized_path="src/main.py")

        build_graph(self.repo_id, [pfile])

        # Query B's callers
        callers = get_callers(self.repo_id, "b")
        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0]["caller"], "a")
        self.assertEqual(callers[0]["edge_type"], "static") # Because both are in the same file

        # Query A's callees
        callees = get_callees(self.repo_id, "a")
        self.assertEqual(len(callees), 1)
        self.assertEqual(callees[0]["callee"], "b")

    def test_defensive_lookups(self):
        build_graph(self.repo_id, [])
        # Querying an empty graph shouldn't raise KeyError
        self.assertEqual(get_callers(self.repo_id, "doesnt_exist"), [])
        self.assertEqual(get_callees(self.repo_id, "doesnt_exist"), [])
        sub = get_subgraph(self.repo_id, "doesnt_exist")
        self.assertEqual(sub["nodes"], [])

    def test_subgraph_clamp(self):
        f1 = ParsedFunction("1", 1, 1, calls=["2"])
        f2 = ParsedFunction("2", 1, 1, calls=["3"])
        f3 = ParsedFunction("3", 1, 1, calls=["4"])
        f4 = ParsedFunction("4", 1, 1, calls=["5"])
        f5 = ParsedFunction("5", 1, 1, calls=[])
        pfile = ParsedFile("src.py", "python", functions=[f1, f2, f3, f4, f5], normalized_path="src.py")

        build_graph(self.repo_id, [pfile])

        # Request depth 10, clamped to 3 server-side
        sub = get_subgraph(self.repo_id, "1", depth=10)
        self.assertEqual(sub["requested_depth"], 10)
        self.assertTrue(sub["clamped"])
        # Depth 3 from "1":
        # 1->2 (hop 1)
        # 2->3 (hop 2)
        # 3->4 (hop 3)
        # 4->5 (hop 4 - excluded)
        node_names = {n["name"] for n in sub["nodes"]}
        self.assertIn("1", node_names)
        self.assertIn("2", node_names)
        self.assertIn("3", node_names)
        self.assertIn("4", node_names)
        self.assertNotIn("5", node_names)

    def test_cycle_timeout(self):
        # Build a large dense cycle manually if needed, or just patch the timeout to be 0
        f_a = ParsedFunction("a", 1, 1, calls=["b"])
        f_b = ParsedFunction("b", 1, 1, calls=["a"])
        pfile = ParsedFile("src.py", "python", functions=[f_a, f_b], normalized_path="src.py")
        build_graph(self.repo_id, [pfile])

        # Normal cycle check works
        has_cycle = detect_cycles(self.repo_id)
        self.assertTrue(has_cycle)

        # Force timeout
        old_timeout = settings.CYCLE_DETECTION_TIMEOUT_S
        settings.CYCLE_DETECTION_TIMEOUT_S = 0.0001
        
        # Force timeout — patch the slow graph check used by detect_cycles.
        with patch("networkx.is_directed_acyclic_graph") as mock_dag:
            import time
            def slow_dag(*_args, **_kwargs):
                time.sleep(0.1)
                return True
            mock_dag.side_effect = slow_dag

            res = detect_cycles(self.repo_id)
            self.assertIsNone(res) # Must be None (null), not False

        settings.CYCLE_DETECTION_TIMEOUT_S = old_timeout

    def test_dangling_edges_prevented(self):
        # "a" calls "missing", but "missing" is not in the parsed files
        f_a = ParsedFunction("a", 1, 1, calls=["missing"])
        pfile = ParsedFile("src.py", "python", functions=[f_a], normalized_path="src.py")
        
        build_graph(self.repo_id, [pfile])
        
        # The edge a->missing must NOT exist in the graph because missing isn't parsed
        callees = get_callees(self.repo_id, "a")
        self.assertEqual(len(callees), 0)

    def test_max_nodes_truncation(self):
        old_max = settings.MAX_GRAPH_NODES
        settings.MAX_GRAPH_NODES = 2
        
        f1 = ParsedFunction("1", 1, 1, calls=[])
        f2 = ParsedFunction("2", 1, 1, calls=[])
        f3 = ParsedFunction("3", 1, 1, calls=[])
        pfile = ParsedFile("src.py", "python", functions=[f1, f2, f3], normalized_path="src.py")
        
        build_graph(self.repo_id, [pfile])
        
        path = _graph_path_for(self.repo_id)
        with path.open() as f:
            data = json.load(f)
            
        self.assertTrue(data["metadata"]["graph_truncated"])
        self.assertEqual(len(data["graph"]["nodes"]), 2)
        
        settings.MAX_GRAPH_NODES = old_max

    def test_atomic_persistence_mid_crash(self):
        # We simulate a crash mid-write by patching json.dump to raise an Exception.
        f1 = ParsedFunction("1", 1, 1, calls=[])
        pfile = ParsedFile("src.py", "python", functions=[f1], normalized_path="src.py")
        
        # 1. Build a valid graph first
        build_graph(self.repo_id, [pfile])
        
        path = _graph_path_for(self.repo_id)
        valid_size = path.stat().st_size
        self.assertGreater(valid_size, 0)
        
        # 2. Try to build a new one, but crash during serialization
        with patch("json.dump", side_effect=RuntimeError("simulated mid-write crash")):
            f2 = ParsedFunction("2", 1, 1, calls=[])
            pfile2 = ParsedFile("src2.py", "python", functions=[f2], normalized_path="src2.py")
            try:
                build_graph(self.repo_id, [pfile2])
            except RuntimeError:
                pass
                
        # 3. Assert the original file is completely untouched (not 0 bytes, not corrupted)
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_size, valid_size)
        
        # And the tmp file might exist, but the main one wasn't partially overwritten
        tmp_path = path.with_suffix(".json.tmp")
        self.assertTrue(tmp_path.exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
