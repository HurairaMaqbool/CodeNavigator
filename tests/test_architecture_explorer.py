# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Unit tests for Call Graph / Architecture Explorer backend endpoints."""

import sys
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import networkx as nx

# Bootstrap mock structlog
sys.modules["structlog"] = MagicMock()

from app.main import app
from app.api.auth import verify_api_key

class TestArchitectureExplorer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[verify_api_key] = lambda: None

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.api.router._resolve_repo_meta")
    @patch("app.api.router._require_repo_ready")
    @patch("app.graph.queries._get_graph")
    def test_get_symbols_success(self, mock_get_graph, mock_ready, mock_meta):
        """GET /symbols/{repo_id} returns all symbols with start/end line coordinates."""
        mock_meta.return_value = (MagicMock(), "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        mock_ready.return_value = None
        
        # Build mock NetworkX graph
        g = nx.DiGraph()
        g.add_node("src/sessions.py:Session.send", name="Session.send", path="src/sessions.py", type="method", start_line=10, end_line=50)
        g.add_node("src/models.py:Response", name="Response", path="src/models.py", type="class", start_line=100, end_line=200)
        mock_get_graph.return_value = g

        resp = self.client.get("/symbols/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        
        # Verify coordinates exist in the payload
        session_send = next(item for item in data if item["name"] == "Session.send")
        self.assertEqual(session_send["start_line"], 10)
        self.assertEqual(session_send["end_line"], 50)
        self.assertEqual(session_send["path"], "src/sessions.py")
        self.assertEqual(session_send["type"], "method")

    @patch("app.api.router._resolve_repo_meta")
    @patch("app.api.router._require_repo_ready")
    @patch("app.api.router.Path.exists")
    @patch("app.api.router.Path.is_file")
    @patch("app.api.router.Path.resolve")
    @patch("app.ingestion.file_filter.safe_decode")
    def test_get_file_snippet_success(self, mock_decode, mock_resolve, mock_is_file, mock_exists, mock_ready, mock_meta):
        """GET /file-snippet/{repo_id} returns correct lines slice and handles path traversal defense."""
        mock_meta.return_value = (MagicMock(), "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        mock_ready.return_value = None
        mock_exists.return_value = True
        mock_is_file.return_value = True
        
        # Mock resolve paths
        mock_resolve.return_value = MagicMock()
        mock_resolve.return_value.relative_to.return_value = True

        # Mock file content
        file_content = "\n".join([f"line {i}" for i in range(1, 21)])
        mock_decode.return_value = (file_content, "utf-8")

        # Query a 1-indexed snippet from lines 10 to 12
        resp = self.client.get(
            "/file-snippet/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            params={"file_path": "src/sessions.py", "start_line": 10, "end_line": 12}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # Check start_line - 1 - 5 to end_line + 5 padding bounds
        self.assertEqual(data["start_line"], 5)
        self.assertEqual(data["end_line"], 17)
        self.assertIn("line 5", data["code"])
        self.assertIn("line 17", data["code"])

    @patch("app.api.router._resolve_repo_meta")
    @patch("app.api.router._require_repo_ready")
    def test_get_file_snippet_path_traversal(self, mock_ready, mock_meta):
        """GET /file-snippet/{repo_id} raises 403 on path traversal attempts."""
        mock_meta.return_value = (MagicMock(), "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        mock_ready.return_value = None
        
        resp = self.client.get(
            "/file-snippet/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            params={"file_path": "../../../etc/passwd"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Forbidden path traversal")
