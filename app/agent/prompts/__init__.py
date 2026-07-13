# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/
------------------
State-specific prompt builders for loop.py (Module #21).

Pure string templates — zero external dependencies, zero LLM calls in this package.
"""
from app.agent.prompts.compress_prompt import compress_prompt
from app.agent.prompts.decide_prompt import decide_prompt
from app.agent.prompts.finalize_prompt import finalize_prompt, finalize_system_prompt
from app.agent.prompts.answer_quality_dataset import (
    classify_query,
    load_dataset,
    render_few_shot_section,
)
from app.agent.prompts.plan_prompt import plan_prompt

__all__ = [
    "plan_prompt",
    "decide_prompt",
    "finalize_prompt",
    "finalize_system_prompt",
    "compress_prompt",
    "classify_query",
    "load_dataset",
    "render_few_shot_section",
]
