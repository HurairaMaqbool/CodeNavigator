# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/answer_quality_dataset.py
-------------------------------------------
Few-shot answer-quality dataset — FORMAT and REASONING PROCESS only.

Chain-of-thought steps guide internal planning. Example claim text is NEVER
injected into the prompt to prevent parroting/hallucination from copied wording.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATASET_PATH = Path(__file__).resolve().parents[3] / "data" / "answer_quality_dataset.json"

QUERY_CATEGORIES: tuple[str, ...] = (
    "FACTUAL",
    "MECHANICAL",
    "REASONING",
    "MULTI_PART",
    "DEEP_CHAIN",
    "ARCHITECTURE",
)

# Skip few-shot when overlap is high but query is not an exact match — parroting risk.
_PARROTING_OVERLAP_THRESHOLD = 0.38


@lru_cache(maxsize=1)
def load_dataset() -> dict[str, Any]:
    """Load and cache the answer-quality dataset JSON."""
    if not _DATASET_PATH.is_file():
        return {}
    return json.loads(_DATASET_PATH.read_text(encoding="utf-8"))


def dataset_available() -> bool:
    """True when the few-shot dataset JSON is present and non-empty."""
    data = load_dataset()
    return bool(data.get("few_shot_examples"))


def classify_query(question: str) -> str:
    """
    Classify a user question into one of the dataset query categories.

    Most-specific categories win (ARCHITECTURE / DEEP_CHAIN before FACTUAL).
    """
    q = question.strip().lower()

    if re.search(
        r"\b(where would you|where in the architecture|where (should|would) (i|we)|"
        r"make changes|custom transport|custom adapter|extension point|"
        r"subclass|override|implement a custom|add a custom)\b",
        q,
    ):
        return "ARCHITECTURE"

    if re.search(
        r"\b(trace what happens|from calling .+ to|call chain|internally when|"
        r"what happens internally|step by step|execution path)\b",
        q,
    ) or re.search(r"\brequests\.(get|post|put|patch|delete|head|options)\b", q):
        return "DEEP_CHAIN"

    from app.retrieval.query_expansion import question_aspect_markers

    if len(question_aspect_markers(question)) >= 2:
        return "MULTI_PART"
    if " and " in q and re.search(r"\b(how|what|why)\b", q):
        if re.search(
            r"\b(retri|timeout|redirect|header|cookie|auth|proxy)\b.*\band\b|"
            r"\band\b.*\b(retri|timeout|redirect|header|cookie|auth|proxy)\b",
            q,
        ):
            return "MULTI_PART"

    from app.retrieval.source_priority import is_reasoning_query

    if is_reasoning_query(question):
        return "REASONING"

    if re.match(r"^how\b", q) or re.search(
        r"\bhow does\b|\bhow is\b|\bhow are\b|\bhow do\b|\bhow would\b",
        q,
    ):
        return "MECHANICAL"

    return "FACTUAL"


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in re.findall(r"[a-z0-9_]{3,}", a.lower())}
    tb = {t for t in re.findall(r"[a-z0-9_]{3,}", b.lower())}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _primary_entities(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b", text))


def _is_parroting_risk(question: str, example: dict[str, Any]) -> bool:
    """True when example query is similar enough to invite wording copy."""
    ex_q = str(example.get("query") or "").strip().lower()
    q_lower = question.strip().lower()
    if ex_q == q_lower:
        return False
    if _token_overlap(q_lower, ex_q) >= _PARROTING_OVERLAP_THRESHOLD:
        return True
    shared = _primary_entities(question) & _primary_entities(str(example.get("query") or ""))
    if not shared:
        return False
    ex_markers = ("difference between", "compare", " vs ", " versus ")
    if any(m in ex_q for m in ex_markers) and not any(m in q_lower for m in ex_markers):
        return True
    return False


def select_few_shot_examples(
    question: str,
    category: str | None = None,
    *,
    max_examples: int = 2,
) -> list[dict[str, Any]]:
    """Return category-matched examples that are safe from parroting risk."""
    data = load_dataset()
    examples: list[dict[str, Any]] = list(data.get("few_shot_examples") or [])
    if not examples:
        return []

    cat = category or classify_query(question)
    q_lower = question.lower()

    def score(ex: dict[str, Any]) -> tuple[int, float, str]:
        if _is_parroting_risk(question, ex):
            return (-1, 0.0, "")
        ex_cat = str(ex.get("category") or "")
        cat_match = 2 if ex_cat == cat else (1 if ex_cat in QUERY_CATEGORIES else 0)
        ex_q = str(ex.get("query") or "")
        overlap = _token_overlap(q_lower, ex_q.lower())
        exact = 3 if ex_q.lower().strip() == q_lower.strip() else 0
        return (exact + cat_match, overlap, str(ex.get("id") or ""))

    ranked = sorted(examples, key=score, reverse=True)
    ranked = [ex for ex in ranked if score(ex)[0] >= 0]
    if not ranked:
        return []

    chosen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for ex in ranked:
        eid = str(ex.get("id") or "")
        if eid in seen_ids:
            continue
        if ex.get("category") == cat or len(chosen) == 0:
            chosen.append(ex)
            seen_ids.add(eid)
        if len(chosen) >= max_examples:
            break

    if len(chosen) < max_examples:
        for ex in ranked:
            eid = str(ex.get("id") or "")
            if eid not in seen_ids:
                chosen.append(ex)
                seen_ids.add(eid)
            if len(chosen) >= max_examples:
                break
    return chosen[:max_examples]


def render_example_block(
    example: dict[str, Any],
    *,
    max_cot_steps: int = 3,
) -> str:
    """Render reasoning steps only — NO example claims or final_answer text."""
    lines: list[str] = [
        f"[{example.get('id')}] category={example.get('category')} — reasoning pattern only",
        f"Sample question type: {example.get('query')}",
        "INTERNAL STEPS (never output; do NOT copy any example answer wording):",
    ]
    cot = list(example.get("chain_of_thought") or [])
    if len(cot) > max_cot_steps:
        cot = cot[:max_cot_steps]
    for step in cot:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def render_few_shot_section(
    question: str,
    category: str | None = None,
    *,
    max_examples: int = 1,
) -> str:
    """Build compact format-only few-shot guidance for FINALIZE."""
    cat = category or classify_query(question)
    examples = select_few_shot_examples(question, cat, max_examples=max_examples)
    if not examples:
        return ""

    blocks = [
        f"QUERY CATEGORY: {cat}",
        "FEW-SHOT = FORMAT + REASONING PROCESS ONLY.",
        "Every claim MUST come from RETRIEVAL CONTEXT below — never from example wording.",
        "",
    ]
    blocks.extend(render_example_block(ex) + "\n" for ex in examples)
    return "\n".join(blocks).strip()


def render_negative_examples_section(*, max_items: int = 3) -> str:
    """Render anti-patterns the model must avoid."""
    data = load_dataset()
    negs = list(data.get("negative_examples_what_not_to_do") or [])[:max_items]
    if not negs:
        return ""

    lines = ["ANTI-PATTERNS:"]
    for neg in negs:
        lines.append(
            f"- [{neg.get('id')}] {neg.get('bad_pattern')} → {neg.get('correct_behavior')}"
        )
    return "\n".join(lines)


def render_pre_answer_checklist(*, compact: bool = True) -> str:
    """Minimal pre-answer self-check — no Urdu template in compact mode."""
    if compact:
        return (
            "BEFORE JSON: (1) Every claim cites RETRIEVAL CONTEXT only. "
            "(2) No copied few-shot wording. (3) src/ not tests/ for implementation. "
            "(4) One distinct fact per claim."
        )
    data = load_dataset()
    items = data.get("pre_answer_checklist") or []
    lines = ["PRE-ANSWER CHECKLIST:"]
    for i, item in enumerate(items, 1):
        lines.append(f"  {i}. {item}")
    return "\n".join(lines)


def finalize_system_quality_prompt(question: str) -> str:
    """Compact system prompt with anti-parroting guard."""
    cat = classify_query(question)
    return (
        "You are a codebase onboarding assistant. "
        "Respond with a single JSON object matching the claims schema. "
        "Use ONLY provided RETRIEVAL CONTEXT — never few-shot example text. "
        "Never copy example phrasing; derive every claim fresh from context. "
        "Abstain honestly when context is insufficient. "
        "Output JSON only — no chain-of-thought. "
        f"Query category: {cat}."
    )
