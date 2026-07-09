# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #32 — voice_input Web Speech API tests."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from frontend.voice_input import (
    AUTO_SUBMIT_PAUSE_MS,
    VOICE_SHORTCUTS,
    _voice_widget_html,
    apply_browser_voice_event,
    on_transcript_final,
    parse_voice_command,
    resolve_voice_submission,
)


def test_parse_voice_command_normal_question():
    cmd = parse_voice_command("How does Session.send work?")
    assert cmd.kind == "normal_question"
    assert cmd.action is None
    assert cmd.text == "How does Session.send work?"


@pytest.mark.parametrize(
    "phrase,action",
    [
        ("explain again", "explain_again"),
        ("ask again", "explain_again"),
        ("repeat that", "explain_again"),
        ("show diagram", "show_diagram"),
        ("generate diagram", "show_diagram"),
    ],
)
def test_parse_voice_shortcuts(phrase, action):
    cmd = parse_voice_command(phrase)
    assert cmd.kind == "shortcut"
    assert cmd.action == action


def test_parse_show_diagram_with_symbol():
    cmd = parse_voice_command("show diagram for Session.send")
    assert cmd.kind == "shortcut"
    assert cmd.action == "show_diagram"
    assert cmd.symbol == "Session.send"


def test_resolve_explain_again_uses_last_user_message():
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
    ]
    out = resolve_voice_submission("explain again", history)
    assert out["route"] == "explain_again"
    assert out["question"] == "first"


def test_resolve_show_diagram_routes_to_diagram_endpoint():
    out = resolve_voice_submission("show diagram for main", [])
    assert out["route"] == "diagram"
    assert out["symbol"] == "main"


def test_resolve_show_diagram_falls_back_to_last_symbol():
    out = resolve_voice_submission("show diagram", [], last_diagram_symbol="app.run")
    assert out["route"] == "diagram"
    assert out["symbol"] == "app.run"


def test_on_transcript_final_includes_pause():
    payload = on_transcript_final("hello world")
    assert payload["text"] == "hello world"
    assert payload["auto_submit_pause_ms"] == AUTO_SUBMIT_PAUSE_MS


def test_widget_html_feature_detects_speech_recognition():
    html = _voice_widget_html(disabled=False, auto_submit_ms=AUTO_SUBMIT_PAUSE_MS)
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in html
    assert "unsupported" in html
    assert "AnalyserNode" not in html  # uses Analyser via createAnalyser
    assert "createAnalyser" in html
    assert str(AUTO_SUBMIT_PAUSE_MS) in html


def test_apply_permission_denied_sets_session_flag():
    st_mock = MagicMock()
    st_mock.session_state = MagicMock()
    with patch("frontend.voice_input.st", st_mock):
        result = apply_browser_voice_event({"type": "permission_denied"}, [])
    assert result is None
    assert st_mock.session_state.voice_permission_denied is True


def test_shortcut_phrase_list_is_fixed():
    phrases = {p for p, _ in VOICE_SHORTCUTS}
    assert phrases == {
        "explain again",
        "ask again",
        "repeat that",
        "show diagram",
        "generate diagram",
    }


def test_widget_posts_base64url_payload():
    html = _voice_widget_html(disabled=False, auto_submit_ms=AUTO_SUBMIT_PAUSE_MS)
    assert "toBase64Url" in html
    assert "vi_payload" in html
    assert "btoa" in html


def test_drain_accepts_base64url_and_plain_json():
    import base64

    from frontend.voice_input import _decode_voice_payload

    plain = _decode_voice_payload(json.dumps({"type": "submit", "text": "hi"}))
    assert plain == {"type": "submit", "text": "hi"}

    raw = base64.urlsafe_b64encode(
        json.dumps({"type": "permission_denied"}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    decoded = _decode_voice_payload(raw)
    assert decoded == {"type": "permission_denied"}
