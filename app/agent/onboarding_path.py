# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/onboarding_path.py
----------------------------
Module #27 — Personalized onboarding learning-path generator.

Ranks architecturally central files from the persisted call graph, generates one
narrow Groq rationale per top file (bounded), verifies via confidence.py, and
caches completed paths per (repo_id, commit_hash, role).
"""
from __future__ import annotations

import concurrent.futures
import json
import re
from pathlib import Path
from typing import Any

import networkx as nx  # type: ignore[import]

from app.agent.confidence import check_file_existence, parse_citations
from app.agent.llm_client import RateLimitError, get_llm_client
from app.config import settings
from app.graph.queries import _get_graph
from app.observability.logging_config import logger

# Bounded Groq spend — never generate rationales for more than this many files.
MAX_RATIONALE_FILES: int = 10

_RATIONALE_TIMEOUT_S: float = 4.0
_RATIONALE_MAX_ATTEMPTS: int = 2
_RATIONALE_MAX_TOKENS: int = 120

# in-degree + out-degree per file (summed across nodes) — files that are heavily
# called and call many others are architectural hubs worth reading first.
_CENTRALITY_MEASURE = "summed_in_out_degree"

_ROLE_PATH_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "backend": [
        re.compile(r"(?:^|/)(?:app|api|server|backend|services?)/", re.I),
        re.compile(r"(?:^|/)src/", re.I),
        re.compile(r"\.py$", re.I),
    ],
    "frontend": [
        re.compile(r"(?:^|/)(?:frontend|client|ui|web|pages?|components?)/", re.I),
        re.compile(r"\.(?:tsx|jsx|vue|svelte)$", re.I),
    ],
    "ml": [
        re.compile(r"(?:^|/)(?:ml|models?|training|notebooks?|data)/", re.I),
        re.compile(r"(?:^|/)app/ml/", re.I),
        re.compile(r"\.ipynb$", re.I),
    ],
}

_EXPERIENCE_TOP_N: dict[str, int] = {
    "junior": 10,
    "beginner": 10,
    "intermediate": 8,
    "mid": 8,
    "senior": 6,
    "expert": 6,
}


def _role_slug(role: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", role.strip().lower())[:32] or "default"


def _cache_path(repo_id: str, commit_hash: str, role: str) -> Path:
    """JSON cache keyed by (repo_id, commit_hash, role) — semantic_cache-style, separate namespace."""
    return (
        Path(settings.REPOS_PATH)
        / repo_id
        / ".onboarding_path_cache"
        / f"{commit_hash[:16]}_{_role_slug(role)}.json"
    )


def _load_cached_path(repo_id: str, commit_hash: str, role: str) -> list[dict[str, Any]] | None:
    path = _cache_path(repo_id, commit_hash, role)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("commit_hash") != commit_hash or payload.get("role") != role:
            return None
        items = payload.get("onboarding_path")
        if isinstance(items, list) and items:
            logger.info("onboarding_path_cache_hit", repo_id=repo_id, role=role)
            return items
    except Exception as exc:
        logger.warning("onboarding_path_cache_read_failed", error=str(exc))
    return None


def _store_cached_path(
    repo_id: str,
    commit_hash: str,
    role: str,
    items: list[dict[str, Any]],
) -> None:
    path = _cache_path(repo_id, commit_hash, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo_id": repo_id,
        "commit_hash": commit_hash,
        "role": role,
        "onboarding_path": items,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    logger.info("onboarding_path_cached", repo_id=repo_id, role=role, steps=len(items))


def _get_commit_hash(repo_id: str) -> str:
    status_file = Path(settings.REPOS_PATH) / repo_id / "sync_status.json"
    if status_file.exists():
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            return str(data.get("commit_hash", ""))
        except Exception:
            pass
    from app.ingestion.metadata_store import metadata_store

    meta = metadata_store.get(repo_id)
    return str(meta.commit_hash or "") if meta else ""


def _file_matches_role(file_path: str, role: str) -> bool:
    patterns = _ROLE_PATH_PATTERNS.get(role.strip().lower(), [])
    if not patterns:
        return True
    normalized = file_path.replace("\\", "/")
    return any(p.search(normalized) for p in patterns)


def _aggregate_file_centrality(graph: nx.DiGraph) -> list[tuple[str, float]]:
    """Sum in-degree + out-degree for all nodes grouped by file ``path`` attribute."""
    scores: dict[str, float] = {}
    in_deg = dict(graph.in_degree())
    out_deg = dict(graph.out_degree())

    for node_id, data in graph.nodes(data=True):
        file_path = str(data.get("path") or node_id.rpartition(":")[0])
        if not file_path:
            continue
        centrality = float(in_deg.get(node_id, 0) + out_deg.get(node_id, 0))
        scores[file_path] = scores.get(file_path, 0.0) + centrality

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked


def _related_functions_for_file(graph: nx.DiGraph, file_path: str) -> list[str]:
    names: list[str] = []
    norm = file_path.replace("\\", "/")
    for node_id, data in graph.nodes(data=True):
        node_path = str(data.get("path") or node_id.rpartition(":")[0]).replace("\\", "/")
        if node_path != norm:
            continue
        name = str(data.get("name") or node_id.rpartition(":")[2])
        if name and name not in names:
            names.append(name)
    return names[:12]


def rank_central_files(graph: nx.DiGraph, role: str) -> list[str]:
    """
    Rank files by summed in/out degree, filtered to ``role`` path conventions.

    Falls back to unfiltered ranking when the role filter matches zero files.
    """
    if graph is None or graph.number_of_nodes() == 0:
        return []

    ranked = _aggregate_file_centrality(graph)
    role_key = role.strip().lower()
    filtered = [path for path, _ in ranked if _file_matches_role(path, role_key)]

    if not filtered and role_key in _ROLE_PATH_PATTERNS:
        logger.info("onboarding_path_role_filter_empty_fallback", role=role_key)
        filtered = [path for path, _ in ranked]

    return filtered


def _safe_rationale_fallback(file_path: str, role: str) -> str:
    return (
        f"`{file_path}` is highly connected in the call graph and is a strong starting "
        f"point for a {role} developer onboarding to this codebase."
    )


def _rationale_passes_file_checks(text: str, repo_id: str, primary_file: str) -> bool:
    """Discard rationales that cite nonexistent files (confidence.py file existence)."""
    cites = parse_citations(text)
    paths_to_check = {primary_file}
    for cite in cites:
        if cite.get("file_path"):
            paths_to_check.add(str(cite["file_path"]))

    for path in paths_to_check:
        ok = check_file_existence({
            "file_path": path,
            "repo_id": repo_id,
            "unparseable": False,
        })
        if not ok:
            return False
    return True


def generate_rationale(file_path: str, role: str, *, repo_id: str, experience_level: str = "") -> str:
    """
    One narrow Groq call explaining why ``file_path`` matters first for ``role``.

    Verified via confidence.py file-existence checks; returns safe fallback on failure.
    """
    if not check_file_existence({
        "file_path": file_path,
        "repo_id": repo_id,
        "unparseable": False,
    }):
        return ""

    prompt = (
        f"You are onboarding a {experience_level or 'new'} {role} developer.\n"
        f"In 1-2 sentences, explain why they should read `{file_path}` first.\n"
        f"Mention only `{file_path}` — do not invent other file paths.\n"
        "Be concrete about architectural role, not generic praise."
    )

    llm = get_llm_client()
    text = ""
    for attempt in range(_RATIONALE_MAX_ATTEMPTS):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    llm.create,
                    system="You write concise onboarding guidance for developers.",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=_RATIONALE_MAX_TOKENS,
                )
                res = future.result(timeout=_RATIONALE_TIMEOUT_S)
            text = "".join(
                block.get("text", "")
                for block in res.content
                if block.get("type") == "text"
            ).strip()
            if text:
                break
        except RateLimitError as exc:
            logger.warning("onboarding_rationale_rate_limited", attempt=attempt + 1, error=str(exc))
        except Exception as exc:
            logger.warning("onboarding_rationale_failed", attempt=attempt + 1, error=str(exc))

    if not text or not _rationale_passes_file_checks(text, repo_id, file_path):
        text = _safe_rationale_fallback(file_path, role)
        if not _rationale_passes_file_checks(text, repo_id, file_path):
            return ""

    return text


def _top_n_for_experience(experience_level: str) -> int:
    key = experience_level.strip().lower()
    return min(MAX_RATIONALE_FILES, _EXPERIENCE_TOP_N.get(key, MAX_RATIONALE_FILES))


def build_path(repo_id: str, role: str, experience_level: str) -> list[dict[str, Any]]:
    """
    Top-level orchestrator — rank, rationale, verify, cache.

    Returns ordered ``{file_path, why_it_matters, suggested_order, related_functions}``.
    """
    commit_hash = _get_commit_hash(repo_id)
    if not commit_hash:
        logger.warning("onboarding_path_missing_commit", repo_id=repo_id)
        return []

    cached = _load_cached_path(repo_id, commit_hash, role)
    if cached is not None:
        return cached

    graph = _get_graph(repo_id)
    if graph is None or graph.number_of_nodes() == 0:
        logger.warning("onboarding_path_empty_graph", repo_id=repo_id)
        return []

    ranked_files = rank_central_files(graph, role)
    if not ranked_files:
        return []

    top_n = _top_n_for_experience(experience_level)
    candidates = ranked_files[:top_n]

    path_items: list[dict[str, Any]] = []
    order = 1
    for file_path in candidates:
        if not check_file_existence({
            "file_path": file_path,
            "repo_id": repo_id,
            "unparseable": False,
        }):
            continue

        rationale = generate_rationale(
            file_path,
            role,
            repo_id=repo_id,
            experience_level=experience_level,
        )
        if not rationale:
            continue

        path_items.append({
            "file_path": file_path,
            "why_it_matters": rationale,
            "suggested_order": order,
            "related_functions": _related_functions_for_file(graph, file_path),
        })
        order += 1

    if not path_items and ranked_files:
        # Last-resort: at least return top unverified file with template (existence-checked only)
        for file_path in ranked_files[:top_n]:
            if check_file_existence({
                "file_path": file_path,
                "repo_id": repo_id,
                "unparseable": False,
            }):
                path_items.append({
                    "file_path": file_path,
                    "why_it_matters": _safe_rationale_fallback(file_path, role),
                    "suggested_order": 1,
                    "related_functions": _related_functions_for_file(graph, file_path),
                })
                break

    if path_items:
        _store_cached_path(repo_id, commit_hash, role, path_items)

    return path_items


def generate_path(repo_id: str, role: str, experience_level: str) -> list[dict[str, Any]]:
    """Backward-compatible alias for router/tests."""
    return build_path(repo_id, role, experience_level)
