"""Module #13 vector_store contract tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.parsing.chunker import CodeChunk


def _chunk(fp: str, text: str = "code") -> CodeChunk:
    path = f"src/{fp}.py"
    return CodeChunk(
        file_path=path,
        display_path=path,
        normalized_path=path,
        function_name=fp,
        class_name="",
        start_line=1,
        end_line=2,
        chunk_text=text,
        type="function",
        language="python",
        fingerprint=fp,
    )


def test_query_missing_repo_returns_empty():
    from app.retrieval.vector_store import query

    with patch("app.retrieval.vector_store.get_collection", return_value=None):
        assert query("missing-repo", [0.1, 0.2, 0.3], top_k=5) == []


def test_upsert_skips_bad_chunk_continues_batch(tmp_path, monkeypatch):
    from app.retrieval import vector_store as vs

    monkeypatch.setattr(vs.settings, "CHROMA_DB_PATH", str(tmp_path / "chroma"))
    vs._CHROMA_CLIENT = None

    good = _chunk("aaa")
    good.vector = [1.0, 0.0]
    bad = _chunk("bbb")

    mock_collection = MagicMock()
    mock_client = MagicMock()
    mock_client.create_collection.return_value = mock_collection

    with patch.object(vs, "_get_client", return_value=mock_client), patch.object(
        vs, "delete_repo"
    ):
        vs.upsert_chunks("repo1", [bad, good])

    mock_client.create_collection.assert_called_once()
    mock_collection.add.assert_called_once()
    assert len(mock_collection.add.call_args.kwargs["ids"]) == 1


def test_upsert_replace_semantics_deletes_first():
    from app.retrieval import vector_store as vs

    good = _chunk("aaa")
    good.vector = [1.0, 0.0]

    with patch.object(vs, "delete_repo") as mock_delete, patch.object(
        vs, "_get_client"
    ) as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.create_collection.return_value = MagicMock()
        vs.upsert_chunks("repo1", [good])

    mock_delete.assert_called_once_with("repo1")
