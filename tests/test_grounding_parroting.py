# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests: anti-parroting, entity retrieval, determinism helpers."""
from __future__ import annotations

from app.agent.prompts.answer_quality_dataset import (
    render_few_shot_section,
    select_few_shot_examples,
)
from app.agent.prompts.finalize_prompt import finalize_prompt
from app.retrieval.entity_retrieval import (
    entity_expansion_needed,
    extract_target_entity,
    expand_entity_hits,
)


def test_few_shot_never_injects_claims_example_text():
    block = render_few_shot_section(
        "What is the responsibility of Session?",
        "FACTUAL",
        max_examples=1,
    )
    assert block
    assert "claims_example" not in block
    assert '"claims"' not in block
    assert "persists cookies, reuses connection pools" not in block
    assert "REASONING PROCESS ONLY" in block or "reasoning pattern" in block


def test_parroting_risk_skips_session_comparison_example():
    """fs_011 must not be selected for Session responsibility — wording overlap risk."""
    examples = select_few_shot_examples(
        "What is the responsibility of Session?",
        "FACTUAL",
        max_examples=2,
    )
    ids = {ex.get("id") for ex in examples}
    assert "fs_011" not in ids


def test_finalize_prompt_anti_parroting_guard():
    prompt = finalize_prompt({
        "question": "What is the responsibility of Session?",
        "assembled_context": "class Session: ...",
        "query_category": "FACTUAL",
    })
    assert "never from example" in prompt.lower() or "never from few-shot" in prompt.lower()
    assert "persists cookies, reuses connection pools" not in prompt


def test_extract_target_entity():
    assert extract_target_entity("What does HTTPAdapter do?") == "HTTPAdapter"
    assert extract_target_entity("What is the responsibility of Session?") == "Session"
    assert extract_target_entity("How are cookies persisted?") is None


def test_entity_expansion_needed():
    assert entity_expansion_needed("What does HTTPAdapter do?")
    assert not entity_expansion_needed("How are cookies persisted across requests?")


def test_expand_entity_hits_returns_merged_list():
    from app.retrieval.hybrid_search import search

    repo = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
    hits = search(repo, "What does HTTPAdapter do?", top_k=5)
    exp = expand_entity_hits(repo, "What does HTTPAdapter do?", hits, max_entity_chunks=12)
    assert isinstance(exp, list)
    assert len(exp) >= len(hits)
