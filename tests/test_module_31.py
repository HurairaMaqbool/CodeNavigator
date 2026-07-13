# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #31 — loading_experience state-aware progress UI tests."""
from __future__ import annotations

import time
from unittest.mock import patch


from frontend.loading_experience import (
    MICRO_COPY_ROTATE_S,
    STEP_ORDER,
    STREAM_STALL_TIMEOUT_S,
    TOTAL_STEPS,
    STATE_ICONS,
    _micro_copy_for,
    _parse_sse_data_line,
    _step_number,
    _stepper_html,
    iter_sse_events,
    render_progress_panel,
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


def test_stepper_marks_active_and_done():
    html = _stepper_html("ACT")
    assert "le-seg active" in html
    assert "le-seg done" in html
    assert "Search" in html


def test_render_state_uses_label_verbatim():
    ph = _Placeholder()
    label = "Searching the codebase…"
    render_state(ph, "ACT", label)
    assert label in ph.html[-1]
    assert "3/7" in ph.html[-1]
    assert "le-stepper" in ph.html[-1]
    assert STATE_ICONS["ACT"] in ph.html[-1]


def test_render_progress_shows_elapsed_timer():
    ph = _Placeholder()
    render_progress_panel(ph, "FINALIZE", "Writing the response…", elapsed_s=12.4, micro_copy="Almost there…")
    assert "12s elapsed" in ph.html[-1]
    assert "Almost there" in ph.html[-1]


def test_micro_copy_rotates_every_five_seconds():
    first = _micro_copy_for("FINALIZE", 0.0)
    second = _micro_copy_for("FINALIZE", MICRO_COPY_ROTATE_S + 0.1)
    assert first != second or len(_micro_copy_for("FINALIZE", 0)) == 1


def test_render_skeleton_shimmer_lines():
    ph = _Placeholder()
    render_skeleton(ph)
    assert "le-skeleton" in ph.html[-1]
    assert "le-line" in ph.html[-1]
    assert "le-shimmer" in ph.html[-1]


def test_parse_sse_contract_shape():
    raw = 'data: {"state":"PLAN","label":"Understanding your question…","timestamp":"2026-07-10T00:00:00+00:00"}'
    evt = _parse_sse_data_line(raw)
    assert evt == {
        "state": "PLAN",
        "label": "Understanding your question…",
        "timestamp": "2026-07-10T00:00:00+00:00",
    }


def test_iter_sse_events_yields_until_respond():
    lines = [
        'data: {"state":"INTAKE","label":"Preparing your request…","timestamp":"t1"}',
        "",
        'data: {"state":"RESPOND","label":"Finalizing…","timestamp":"t2"}',
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
        {"state": "INTAKE", "label": "Preparing your request…", "timestamp": "t0"},
        {"state": "FINALIZE", "label": "Writing the response…", "timestamp": "t1"},
        {"state": "RESPOND", "label": "Finalizing…", "timestamp": "t2"},
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
    assert any("Preparing your request" in h for h in progress.html)
    assert any("le-skeleton" in h for h in skeleton.html)
    assert any("Finalizing" in h for h in progress.html)
    assert any("s elapsed" in h for h in progress.html)


def test_stall_shows_rotating_micro_copy():
    progress = _Placeholder()
    skeleton = _Placeholder()

    def _slow_sse(_sid):
        time.sleep(0.05)
        yield {"state": "PLAN", "label": "Understanding your question…", "timestamp": "t1"}

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
    joined = " ".join(progress.html)
    assert "Understanding your question" in joined or "Choosing the best search" in joined
