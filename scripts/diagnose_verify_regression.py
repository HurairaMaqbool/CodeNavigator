"""Diagnose verification regression — structural, cited text, batch verify."""
from __future__ import annotations

from app.agent.confidence import _load_repo_metadata, path_key
from app.agent.claim_verification import (
    _line_range_ok,
    _structural_ok,
    fetch_cited_text,
    verify_claims_batch,
)
from app.retrieval.hybrid_search import search

REPO = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"


def main() -> None:
    hits = search(REPO, "connection pooling performance", top_k=8)
    print(f"hits={len(hits)}")
    allowed = {
        path_key(
            str(
                (h.get("chunk_metadata") or {}).get("display_path")
                or (h.get("chunk_metadata") or {}).get("file_path")
                or ""
            )
        )
        for h in hits
    }
    allowed.discard("")

    for h in hits[:3]:
        m = h.get("chunk_metadata") or {}
        p = m.get("display_path") or m.get("file_path")
        s = int(m.get("start_line") or 1)
        e = int(m.get("end_line") or s)
        cite = {"file_path": p, "start_line": s, "end_line": e}
        print(f"\n--- hit {p} L{s}-{e}")
        print("  line_ok:", _line_range_ok(cite, REPO, allowed_paths=allowed))
        print("  struct:", _structural_ok(cite, REPO, allowed_paths=allowed))
        print("  cited_len:", len(fetch_cited_text(REPO, p, s, e, retrieval_hits=hits)))
        print("  hit.chunk_len:", len(str(h.get("chunk") or "")))

    meta = _load_repo_metadata(REPO)
    rec = next(
        r for r in meta if "sessions.py" in str(r.get("display_path") or r.get("file_path"))
    )
    p = rec.get("display_path") or rec.get("file_path")
    s, e = int(rec["start_line"]), int(rec["end_line"])
    cite = {"file_path": p, "start_line": s, "end_line": e}
    print(f"\n--- bm25 record {p} L{s}-{e}")
    print("  line_ok:", _line_range_ok(cite, REPO, allowed_paths=allowed))
    print("  struct:", _structural_ok(cite, REPO, allowed_paths=allowed))
    print("  cited_len (no hits):", len(fetch_cited_text(REPO, p, s, e)))
    print("  cited_len (with hits):", len(fetch_cited_text(REPO, p, s, e, retrieval_hits=hits)))

    claims = [
        {
            "claim": "Session uses HTTP adapters for connection pooling.",
            "citation": cite,
        }
    ]
    vr = verify_claims_batch(claims, REPO, retrieval_hits=hits, allowed_paths=allowed)
    print("\nverify_batch:", vr)


if __name__ == "__main__":
    main()
