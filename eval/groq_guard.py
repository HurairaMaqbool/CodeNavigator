# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/groq_guard.py
------------------
Pre-flight Groq availability checks so eval aborts early with a clear
message instead of storing meaningless all-zero RAGAS scores.
"""
from __future__ import annotations

import time
from typing import Any

from app.config import settings


class GroqQuotaError(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def probe_groq_available() -> tuple[bool, str]:
    """
    Minimal Groq call to verify the org has quota before a long eval run.
    Returns (ok, message).
    """
    if settings.LLM_PROVIDER != "groq":
        return True, "non-groq provider"

    api_key = (settings.GROQ_API_KEY or "").strip()
    if not api_key:
        return False, "GROQ_API_KEY is not set"

    model = settings.EVAL_JUDGE_MODEL or settings.LLM_MODEL
    try:
        from langchain_groq import ChatGroq

        llm = ChatGroq(model=model, groq_api_key=api_key, temperature=0, max_tokens=8)
        llm.invoke("ping")
        return True, f"Groq OK ({model})"
    except Exception as exc:
        err = str(exc).lower()
        if "rate_limit" in err or "429" in err:
            return False, f"Groq quota/rate limit: {exc}"
        return False, f"Groq probe failed: {exc}"


def require_groq_quota() -> None:
    ok, msg = probe_groq_available()
    if not ok:
        raise GroqQuotaError(
            f"Evaluation blocked: {msg}\n"
            "Wait for daily quota reset, use llama-3.1-8b-instant, or set LLM_PROVIDER=ollama.",
            details={"probe_message": msg},
        )


def eval_question_delay() -> None:
    """Pause between agent calls to avoid TPM bursts on free tier."""
    delay = float(settings.EVAL_QUESTION_DELAY_S)
    if delay > 0:
        time.sleep(delay)
