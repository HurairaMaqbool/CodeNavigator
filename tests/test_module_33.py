# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #33 — voice_output SpeechSynthesis tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from frontend.voice_output import (
    VOICE_OUTPUT_SESSION_KEY,
    _tts_widget_html,
    is_voice_output_enabled,
    speak,
    strip_for_speech,
    toggle_voice_output,
)


def test_strip_citation_to_according_to_basename():
    text = "Auth lives in `src/auth/sessions.py:120-134` and validates tokens."
    out = strip_for_speech(text)
    assert "according to sessions.py" in out
    assert "120" not in out
    assert "134" not in out
    assert "`" not in out


def test_strip_markdown_headers_bold_bullets_fences():
    text = """## Overview
**Bold** and *italic* matter.
- first bullet
1. numbered
```python
x = 1
```
See [docs](https://example.com).
"""
    out = strip_for_speech(text)
    assert "##" not in out
    assert "**" not in out
    assert "*" not in out or "italic" in out
    assert "```" not in out
    assert "x = 1" not in out
    assert "https://example.com" not in out
    assert "docs" in out
    assert "first bullet" in out
    assert "numbered" in out


def test_strip_bare_citation_without_backticks():
    out = strip_for_speech("Defined in app/loop.py:42-50.")
    assert "according to loop.py" in out
    assert ":42" not in out


def test_toggle_voice_output_session_only():
    st_mock = MagicMock()
    st_mock.session_state = {}
    with patch("frontend.voice_output.st", st_mock):
        toggle_voice_output(True)
        assert st_mock.session_state[VOICE_OUTPUT_SESSION_KEY] is True
        assert is_voice_output_enabled() is True
        toggle_voice_output(False)
        assert st_mock.session_state[VOICE_OUTPUT_SESSION_KEY] is False


def test_tts_widget_feature_detects_and_cancels():
    html = _tts_widget_html("hello world", language="en-US", autoplay=False)
    assert "speechSynthesis" in html
    assert "SpeechSynthesisUtterance" in html
    assert "unsupported" in html
    assert "speechSynthesis.cancel()" in html
    assert "hello world" in html


def test_speak_returns_none_and_strips_before_widget():
    mock_components = MagicMock()
    with patch("frontend.voice_output.components", mock_components):
        result = speak("See `foo.py:1-2` for details.", language="en-US")
        mock_components.html.assert_called_once()
        html_arg = mock_components.html.call_args[0][0]
        assert "according to foo.py" in html_arg
        assert "foo.py:1-2" not in html_arg
    assert result is None


def test_speak_skips_empty_after_strip():
    mock_components = MagicMock()
    with patch("frontend.voice_output.components", mock_components):
        speak("   ")
        mock_components.html.assert_not_called()
