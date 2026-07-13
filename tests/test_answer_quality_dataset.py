# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Tests for few-shot + chain-of-thought answer quality dataset integration."""
from __future__ import annotations

from app.config import settings
from app.agent.prompts.answer_quality_dataset import (
    classify_query,
    load_dataset,
    render_few_shot_section,
    render_negative_examples_section,
    render_pre_answer_checklist,
    select_few_shot_examples,
)
from app.agent.prompts.finalize_prompt import finalize_prompt, finalize_system_prompt


def test_dataset_loads_with_fourteen_examples():
    data = load_dataset()
    assert data.get("dataset_name")
    assert len(data.get("few_shot_examples") or []) >= 14
    assert len(data.get("negative_examples_what_not_to_do") or []) >= 5


def test_classify_golden_questions():
    assert classify_query("What does HTTPAdapter do?") == "FACTUAL"
    assert classify_query(
        "Why does Requests use urllib3 instead of implementing HTTP from scratch?"
    ) == "REASONING"
    assert classify_query("How are retries and timeouts handled?") == "MULTI_PART"
    assert classify_query("What happens internally when requests.get(url) is called?") == "DEEP_CHAIN"
    assert classify_query(
        "If you wanted to add a custom transport layer or retry mechanism, where would you make changes?"
    ) == "ARCHITECTURE"
    assert classify_query("How are cookies persisted across requests?") == "MECHANICAL"


def test_select_few_shot_prefers_category_match():
    q = "How are retries and timeouts handled?"
    examples = select_few_shot_examples(q, "MULTI_PART", max_examples=2)
    assert examples
    assert examples[0].get("id") == "fs_003"


def test_render_few_shot_includes_cot_not_in_output_instruction():
    block = render_few_shot_section(
        "What does HTTPAdapter do?",
        "FACTUAL",
        max_examples=1,
    )
    assert "INTERNAL STEPS" in block or "INTERNAL CHAIN-OF-THOUGHT" in block
    assert "never output" in block.lower() or "do NOT copy" in block
    assert "fs_001" in block
    assert "persists cookies" not in block


def test_negative_examples_rendered():
    block = render_negative_examples_section()
    assert "neg_001" in block
    assert "tests/" in block.lower()


def test_pre_answer_checklist_rendered():
    block = render_pre_answer_checklist()
    assert "RETRIEVAL CONTEXT" in block or "PRE-ANSWER" in block


def test_finalize_prompt_injects_dataset_sections():
    prompt = finalize_prompt({
        "question": "Why does Requests use urllib3 instead of implementing HTTP from scratch?",
        "assembled_context": "sample context",
        "is_why_query": True,
        "query_category": "REASONING",
    })
    assert "FEW-SHOT GUIDANCE" in prompt or "FEW-SHOT =" in prompt
    assert "ANTI-PATTERNS" in prompt
    assert "persists cookies" not in prompt
    assert "WHY-QUESTION MODE" in prompt


def test_finalize_system_prompt_includes_category():
    system = finalize_system_prompt(
        "How are retries and timeouts handled?"
    )
    assert "MULTI_PART" in system
    assert "JSON" in system


def test_finalize_prompt_stays_under_groq_tpm_budget():
    from app.agent.prompts.finalize_prompt import estimate_finalize_input_tokens

    big_context = "x" * 20000
    for question in (
        "How are retries and timeouts handled?",
        "What happens internally when requests.get(url) is called?",
    ):
        tokens = estimate_finalize_input_tokens(question, big_context)
        assert tokens <= int(settings.GROQ_FINALIZE_MAX_INPUT_TOKENS), (
            f"FINALIZE prompt too large for {question!r}: {tokens} tokens"
        )
