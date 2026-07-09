# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #31 — loading_experience state-aware progress UI tests."""
from __future__ import annotations

import json
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from frontend.loading_experience import (
    STEP_ORDER,
    STILL_WORKING_LABEL,
    STREAM_STALL_TIMEOUT_S,
    TOTAL_STEPS,
    STATE_ICONS,
    _parse_sse_data_line,
    _step_number,
    iter_sse_events,
    render_skeleton,
    render_state,
    run_chat_with_loading,
)


class _Placeholder:
    def __init__(self) -> None:
        self.html: list[str] = []

    def markdown(self, body: str, *, unsafe_allow_html: bool = False) -> None:
        self.html.append(body)

    def empty(self) -> None:
        self.html.clear()


def test_step_mapping_seven_states():
    assert TOTAL_STEPS == 7
    assert len(STEP_ORDER) == 7
    assert _step_number("INTAKE") == 1
    assert _step_number("VERIFY") == 7
    assert _step_number("RESPOND") == 7


def test_render_state_uses_label_verbatim():
    ph = _Placeholder()
    label = "Searching the codebase…"
    render_state(ph, "ACT", label)
    assert label in ph.html[-1]
    assert "Step 3 of 7" in ph.html[-1]
    assert STATE_ICONS["ACT"] in ph.html[-1]


def test_render_skeleton_only_placeholder_lines():
    ph = _Placeholder()
    render_skeleton(ph)
    assert "le-skeleton" in ph.html[-1]
    assert "le-line" in ph.html[-1]


def test_parse_sse_contract_shape():
    raw = 'data: {"state":"PLAN","label":"Planning the best approach…","timestamp":"2026-07-10T00:00:00+00:00"}'
    evt = _parse_sse_data_line(raw)
    assert evt == {
        "state": "PLAN",
        "label": "Planning the best approach…",
        "timestamp": "2026-07-10T00:00:00+00:00",
    }


def test_iter_sse_events_yields_until_respond():
    lines = [
        'data: {"state":"INTAKE","label":"Understanding your question…","timestamp":"t1"}',
        "",
        'data: {"state":"RESPOND","label":"Delivering your answer…","timestamp":"t2"}',
        'data: {"state":"EXTRA","label":"ignored","timestamp":"t3"}',
    ]

    class _FakeResp:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            yield from lines

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("frontend.loading_experience.requests.get", return_value=_FakeResp()):
        events = list(iter_sse_events("sess-x"))
    assert len(events) == 2
    assert events[0]["state"] == "INTAKE"
    assert events[1]["state"] == "RESPOND"


def test_run_chat_shows_bootstrap_then_final_answer():
    progress = _Placeholder()
    skeleton = _Placeholder()
    events = [
        {"state": "INTAKE", "label": "Understanding your question…", "timestamp": "t0"},
        {"state": "FINALIZE", "label": "Drafting your answer…", "timestamp": "t1"},
        {"state": "RESPOND", "label": "Delivering your answer…", "timestamp": "t2"},
    ]

    def _fake_iter(_sid):
        yield from events

    def _fake_chat(repo_id, question, session_id=None):
        time.sleep(0.05)
        return {"answer": "done", "gated": False, "sources": [{"file_path": "a.py"}]}

    with patch("frontend.loading_experience.iter_sse_events", side_effect=_fake_iter):
        ans = run_chat_with_loading(
            progress,
            skeleton,
            session_id="s1",
            repo_id="r1",
            question="q",
            chat_callable=_fake_chat,
        )

    assert ans["answer"] == "done"
    assert any("Understanding your question" in h for h in progress.html)
    assert any("le-skeleton" in h for h in skeleton.html)
    assert any("Delivering your answer" in h for h in progress.html)


def test_stall_fallback_still_working():
    progress = _Placeholder()
    skeleton = _Placeholder()

    def _slow_sse(_sid):
        time.sleep(0.05)
        yield {"state": "PLAN", "label": "Planning the best approach…", "timestamp": "t1"}

    def _slow_chat(repo_id, question, session_id=None):
        time.sleep(STREAM_STALL_TIMEOUT_S + 0.5)
        return {"answer": "late", "gated": False}

    with patch("frontend.loading_experience.iter_sse_events", side_effect=_slow_sse), patch(
        "frontend.loading_experience.STREAM_STALL_TIMEOUT_S", 0.15
    ):
        ans = run_chat_with_loading(
            progress,
            skeleton,
            session_id="s2",
            repo_id="r1",
            question="q",
            chat_callable=_slow_chat,
        )

    assert ans["answer"] == "late"
    assert any(STILL_WORKING_LABEL in h for h in progress.html)
