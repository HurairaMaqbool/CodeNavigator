# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

from eval.retrieval_metrics import collect_cited_files, paths_match


def test_collect_cited_files_reads_chunk_metadata_hits():
    res = {
        "sources": [],
        "retrieval_hits": [
            {
                "chunk_metadata": {
                    "file_path": "src/flask/ctx.py",
                    "display_path": "src/flask/ctx.py",
                }
            }
        ],
        "answer": "",
    }
    files = collect_cited_files(res, top_k=5)
    assert any(paths_match(f, "src/flask/ctx.py") for f in files)
