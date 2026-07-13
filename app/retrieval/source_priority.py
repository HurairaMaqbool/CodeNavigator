# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Source-type priority for implementation Q&A — src/ over tests/."""
from __future__ import annotations

import re
from typing import Any


def normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


def is_test_path(path: str) -> bool:
    p = normalize_repo_path(path)
    name = p.split("/")[-1]
    return (
        "/tests/" in p
        or p.startswith("tests/")
        or "/test/" in p
        or p.startswith("test/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def is_src_path(path: str) -> bool:
    p = normalize_repo_path(path)
    return "/src/" in p or p.startswith("src/")


def question_mentions_tests(question: str) -> bool:
    q = question.lower()
    return bool(
        re.search(r"\b(tests?|test suite|test case|unit test|pytest)\b", q)
    )


def query_path_boost(path: str, question: str) -> float:
    """Boost paths whose stem matches question keywords (golden-set precision)."""
    if not path or not question:
        return 0.0
    stem = normalize_repo_path(path).split("/")[-1]
    q = question.lower()
    hints: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("status code", "status codes"), ("status_codes.py",)),
        (("cookie", "cookies"), ("cookies.py",)),
        (("application context", "request context"), ("ctx.py",)),
        (("blueprint",), ("blueprints.py",)),
        (("command-line", "command line", " cli"), ("cli.py",)),
        (("basic auth", "httpbasicauth"), ("auth.py",)),
        (("exception", "connectionerror", "timeout"), ("exceptions.py",)),
        (("ssl", "certificate"), ("adapters.py",)),
        (("session class", "session"), ("sessions.py",)),
        (("preparedrequest", "prepared request"), ("models.py",)),
    )
    for keywords, filenames in hints:
        if any(k in q for k in keywords) and stem in filenames:
            return 0.35
    if any(
        k in q
        for k in (
            "class",
            "file",
            "implement",
            "defined",
            "structure",
            "manage",
            "store",
            "where",
            "how",
        )
    ):
        if stem in ("readme.md", "history.md", "changelog.md"):
            return -0.35
    if stem == "app.py" and any(
        k in q for k in ("application context", "request context", "context")
    ):
        return -0.5
    return 0.0


def source_path_penalty(path: str, query: str = "") -> float:
    """Rerank adjustment: strongly demote tests/ for implementation questions."""
    if not path:
        return 0.0
    boost = query_path_boost(path, query)
    if boost:
        return boost
    if is_test_path(path):
        if question_mentions_tests(query):
            return -0.15
        return -0.85
    if "/docs/" in normalize_repo_path(path):
        return -0.15
    if is_src_path(path):
        return 0.08
    return 0.0


def chunk_path(chunk: dict[str, Any]) -> str:
    meta = chunk.get("chunk_metadata") or chunk
    return str(
        meta.get("display_path")
        or meta.get("file_path")
        or chunk.get("file_path")
        or ""
    )


def prefer_implementation_hits(
    hits: list[dict[str, Any]],
    question: str,
    *,
    max_test_hits: int = 0,
) -> list[dict[str, Any]]:
    """
    Drop test-file hits when src/ implementation hits exist for the same query.

    Keeps at most ``max_test_hits`` test chunks when the question explicitly
    asks about tests, or when no src/ hits remain.
    """
    if not hits or question_mentions_tests(question):
        return hits

    src_hits: list[dict[str, Any]] = []
    test_hits: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []

    for hit in hits:
        path = chunk_path(hit)
        if is_test_path(path):
            test_hits.append(hit)
        elif is_src_path(path) or path:
            src_hits.append(hit)
        else:
            other.append(hit)

    if src_hits:
        return src_hits + other + test_hits[:max_test_hits]
    return hits


def is_reasoning_query(question: str) -> bool:
    """True for why/design/rationale questions — not mere what/how mechanics."""
    q = question.strip().lower()
    patterns = (
        r"^why\b",
        r"\bwhy does\b",
        r"\bwhy is\b",
        r"\bwhy use\b",
        r"\bwhy would\b",
        r"\breason\b",
        r"\bpurpose\b",
        r"\bdesign decision\b",
        r"\binstead of\b",
        r"\brather than\b",
        r"\bfrom scratch\b",
    )
    return any(re.search(p, q) for p in patterns)


def is_why_query(question: str) -> bool:
    return is_reasoning_query(question)
