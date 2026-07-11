"""Full VERIFY path diagnostic with mocked Groq — no API calls."""
from __future__ import annotations

import json
import time
import traceback
from unittest.mock import patch

from app.agent.loop import run
from app.retrieval.hybrid_search import search

REPO = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"

QUESTIONS = [
    "How does connection pooling improve performance?",
    "What happens internally when requests.get(url) is called?",
    "How request parameters are validated and processed",
    "The role of urllib3.PoolManager",
]


def _build_finalize_json(question: str) -> str:
    hits = search(REPO, question, top_k=5)
    claims = []
    for h in hits[:3]:
        m = h.get("chunk_metadata") or {}
        p = m.get("display_path") or m.get("file_path")
        if not p:
            continue
        s = int(m.get("start_line") or 1)
        e = int(m.get("end_line") or s)
        snippet = str(h.get("chunk") or "")[:200]
        claims.append({
            "claim": f"The codebase shows relevant behavior in `{p}` (lines {s}-{e}): {snippet[:80]}…",
            "citation": {"file_path": p, "start_line": s, "end_line": e},
        })
    if not claims:
        claims = [{"claim": "Insufficient context in indexed chunks.", "citation": None}]
    return json.dumps({"claims": claims})


def _mock_groq(system, user, **kwargs):
    purpose = kwargs.get("purpose", "")
    if purpose == "decide":
        return "YES"
    if purpose == "finalize":
        # Extract question from user prompt heuristically
        for q in QUESTIONS:
            if q[:20] in user:
                return _build_finalize_json(q)
        return _build_finalize_json(QUESTIONS[0])
    return "YES"


def main() -> None:
    with patch("app.agent.loop._groq_text", side_effect=_mock_groq), patch(
        "app.agent.loop.semantic_cache_lookup", return_value=None
    ), patch("app.agent.loop.semantic_cache_store"), patch(
        "app.agent.loop._exact_question_cache_get", return_value=None
    ):
        for q in QUESTIONS:
            t0 = time.time()
            try:
                out = run(REPO, q, "diag-session", job_id=JOB)
            except Exception:
                print(f"Q: {q}\n  EXCEPTION:\n{traceback.format_exc()}\n")
                continue
            elapsed = time.time() - t0
            print(f"Q: {q}")
            print(f"  time={elapsed:.1f}s gated={out.get('gated')} score={out.get('confidence_score')}")
            print(f"  answer={(out.get('answer') or '')[:200]!r}")
            print()


if __name__ == "__main__":
    main()
