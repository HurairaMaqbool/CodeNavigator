"""
tests/test_diagrams.py
----------------------
Unit tests for Module 11 (Mermaid Diagram Generation).

Run with:
    python -m unittest tests/test_diagrams.py -v
"""
from __future__ import annotations

import unittest
from app.diagrams.mermaid_generator import graph_to_mermaid, sanitize

class TestDiagramGenerator(unittest.TestCase):
    def test_sanitize_collisions(self):
        seen: dict[str, str] = {}
        s1 = sanitize("auth.validate", seen)
        s2 = sanitize("auth_validate", seen)
        
        # They map to the same safe base "auth_validate", so the second one should be disambiguated
        self.assertEqual(s1, "auth_validate")
        self.assertEqual(s2, "auth_validate_1")

    def test_graph_to_mermaid_basic(self):
        subgraph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b"}]
        }
        res = graph_to_mermaid(subgraph, requested_depth=2, clamped_depth=2)
        
        self.assertFalse(res["clamped"])
        self.assertIn("a[\"a\"] --> b[\"b\"]", res["mermaid"])
        self.assertNotIn("more dependencies not shown", res["mermaid"])

    def test_graph_to_mermaid_edgeless(self):
        # Zero edges but nodes present: render isolated nodes (not empty)
        subgraph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": []
        }
        res = graph_to_mermaid(subgraph, requested_depth=2, clamped_depth=2)
        
        self.assertFalse(res.get("empty"))
        self.assertIn("graph TD", res["mermaid"])
        self.assertIn('a["a"]', res["mermaid"])

    def test_graph_to_mermaid_self_loop(self):
        subgraph = {
            "nodes": [{"id": "a"}],
            "edges": [{"source": "a", "target": "a"}]
        }
        res = graph_to_mermaid(subgraph, requested_depth=2, clamped_depth=2)
        
        self.assertIn("a[\"a\"] --> a[\"a\"]", res["mermaid"])

    def test_graph_to_mermaid_max_nodes_truncation(self):
        subgraph = {
            "nodes": [{"id": str(i)} for i in range(10)],
            "edges": [{"source": str(i), "target": str(i+1)} for i in range(9)]
        }
        res = graph_to_mermaid(subgraph, requested_depth=2, clamped_depth=2, max_nodes=5)
        
        # It should cap at 5 nodes
        self.assertIn("+5 more dependencies not shown", res["mermaid"])
        
        # The edges between nodes 0-4 should be present
        self.assertIn("0[\"0\"] --> 1[\"1\"]", res["mermaid"])
        
        # Edges involving node 5+ should be missing
        self.assertNotIn("5[\"5\"]", res["mermaid"])

    def test_clamped_flag_independent_of_node_count(self):
        subgraph = {
            "nodes": [{"id": "a"}],
            "edges": []
        }
        # Requested 10, clamped to 3. But the graph is tiny (1 node).
        res = graph_to_mermaid(subgraph, requested_depth=10, clamped_depth=3)
        
        # Clamped is True (depth was restricted); single node still renders
        self.assertTrue(res["clamped"])
        self.assertFalse(res.get("empty"))
        self.assertIn("graph TD", res["mermaid"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
