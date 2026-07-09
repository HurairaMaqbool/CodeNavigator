# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/voice_output.py
------------------------
Module #33 — Browser-native text-to-speech for chat answers (SpeechSynthesis).

Strips markdown/citation syntax into speakable prose, then plays via
``window.speechSynthesis`` / ``SpeechSynthesisUtterance``. No audio leaves
the client; no third-party TTS SDK.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

# Session-scoped preference key (Streamlit ``st.session_state`` only).
VOICE_OUTPUT_SESSION_KEY = "voice_output_enabled"

# Citation: `path/to/file.py:12-34` or bare path:lines inside backticks.
_CITATION_RE = re.compile(
    r"`([^`\n]+?):(\d+)(?:-(\d+))?`",
)
_BARE_CITATION_RE = re.compile(
    r"(?<![\w/.-])([\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|rb|md|yml|yaml|toml|json|css|html))"
    r":(\d+)(?:-(\d+))?",
)

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BOLD_ITALIC_RE = re.compile(r"(\*\*\*|___|\*\*|__|\*|_)(.*?)\1")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BULLET_RE = re.compile(r"^[\s]*[-*•]\s+", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^[\s]*\d+\.\s+", re.MULTILINE)
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _basename(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    return cleaned.rsplit("/", 1)[-1] if cleaned else path


def _citation_to_spoken(match: re.Match[str]) -> str:
    """``sessions.py:120-134`` → ``according to sessions.py`` (line numbers dropped)."""
    return f"according to {_basename(match.group(1))}"


def strip_for_speech(answer_text: str) -> str:
    """
    Deterministic markdown/citation strip before SpeechSynthesis.

    Strips / transforms:
    - citations ``file_path:start-end`` → ``according to <basename>``
    - fenced code blocks (``` … ```) → removed
    - remaining inline backticks → inner text only
    - AT headers (``#`` … ``######``)
    - bold/italic markers (``*`` / ``_`` wrappers)
    - markdown links ``[label](url)`` → label
    - bullet / numbered list markers
    - collapsed excess whitespace
    """
    if not answer_text:
        return ""

    text = answer_text
    text = _CITATION_RE.sub(_citation_to_spoken, text)
    text = _BARE_CITATION_RE.sub(_citation_to_spoken, text)
    text = _CODE_FENCE_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _HEADER_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    # Bold/italic: peel wrappers repeatedly.
    for _ in range(4):
        text = _BOLD_ITALIC_RE.sub(r"\2", text)
    text = _BULLET_RE.sub("", text)
    text = _NUMBERED_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def toggle_voice_output(enabled: bool) -> None:
    """Persist on/off for the current Streamlit session only (``st.session_state``)."""
    st.session_state[VOICE_OUTPUT_SESSION_KEY] = bool(enabled)


def is_voice_output_enabled() -> bool:
    return bool(st.session_state.get(VOICE_OUTPUT_SESSION_KEY, False))


def speak(answer_text: str, language: str = "en-US") -> None:
    """
    Strip markdown/citations, then play via browser SpeechSynthesis.

    Returns nothing — purely an output-side side effect. Renders a widget that
    feature-detects ``window.speechSynthesis`` and hides itself if unsupported.
    Stop control uses ``speechSynthesis.cancel()`` (immediate halt; clearer than
    ``pause()`` which leaves a resumable utterance mid-sentence).
    """
    speakable = strip_for_speech(answer_text)
    if not speakable:
        return
    components.html(
        _tts_widget_html(speakable, language=language, autoplay=True),
        height=56,
        scrolling=False,
    )


def render_read_aloud_controls(
    answer_text: str,
    *,
    language: str = "en-US",
    autoplay: bool | None = None,
) -> None:
    """
    Manual read-aloud button + stop control for a final answer.

    When ``autoplay`` is None, uses the session toggle from ``toggle_voice_output``.
    """
    if not answer_text or not str(answer_text).strip():
        return
    speakable = strip_for_speech(answer_text)
    if not speakable:
        return
    do_auto = is_voice_output_enabled() if autoplay is None else bool(autoplay)
    components.html(
        _tts_widget_html(speakable, language=language, autoplay=do_auto),
        height=56,
        scrolling=False,
    )


def render_voice_output_toggle() -> None:
    """Sidebar/session toggle — persists via ``toggle_voice_output``."""
    current = is_voice_output_enabled()
    enabled = st.checkbox(
        "Read answers aloud",
        value=current,
        key="voice_output_toggle_ui",
        help="Uses the browser SpeechSynthesis API — nothing is uploaded.",
    )
    if enabled != current:
        toggle_voice_output(enabled)


def _tts_widget_html(speakable: str, *, language: str, autoplay: bool) -> str:
    # Embed speakable text as JSON so quotes/newlines cannot break the script.
    payload = json.dumps({"text": speakable, "lang": language, "autoplay": autoplay})
    safe_payload = html.escape(payload, quote=True)
    try:
        from theme import widget_style_tokens
    except ImportError:
        from frontend.theme import widget_style_tokens

    t = widget_style_tokens()
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; font-family: {t["font_family"]}; }}
  body {{ margin: 0; padding: 4px 2px; background: transparent; }}
  #vo-root.unsupported {{ display: none !important; }}
  #vo-bar {{
    display: flex; align-items: center; gap: 8px;
  }}
  button {{
    border: none; border-radius: 8px; padding: 6px 12px; font-size: 0.82rem;
    cursor: pointer; font-weight: 600;
  }}
  #speak-btn {{ background: {t["info_bg"]}; color: {t["info_fg"]}; }}
  #stop-btn {{
    background: {t["danger_bg"]}; color: {t["danger"]}; display: none;
  }}
  #stop-btn.visible {{ display: inline-block; }}
  #vo-status {{ font-size: 0.78rem; color: {t["text_muted"]}; }}
</style>
</head>
<body>
<div id="vo-root">
  <div id="vo-bar">
    <button id="speak-btn" type="button" title="Read aloud">🔊 Read aloud</button>
    <button id="stop-btn" type="button" title="Stop speaking">⏹ Stop</button>
    <span id="vo-status"></span>
  </div>
</div>
<script type="application/json" id="vo-payload">{safe_payload}</script>
<script>
(function() {{
  const root = document.getElementById('vo-root');
  const speakBtn = document.getElementById('speak-btn');
  const stopBtn = document.getElementById('stop-btn');
  const status = document.getElementById('vo-status');
  const raw = document.getElementById('vo-payload').textContent;
  let cfg;
  try {{ cfg = JSON.parse(raw); }} catch (e) {{ root.classList.add('unsupported'); return; }}

  if (!('speechSynthesis' in window) || typeof window.SpeechSynthesisUtterance === 'undefined') {{
    root.classList.add('unsupported');
    return;
  }}

  let speaking = false;

  function setSpeaking(on) {{
    speaking = on;
    if (on) {{
      stopBtn.classList.add('visible');
      status.textContent = 'Speaking…';
    }} else {{
      stopBtn.classList.remove('visible');
      status.textContent = '';
    }}
  }}

  function stopSpeaking() {{
    // cancel() immediately ends playback; pause() would leave a resumable mid-utterance.
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }}

  function speak() {{
    stopSpeaking();
    const u = new SpeechSynthesisUtterance(cfg.text || '');
    u.lang = cfg.lang || 'en-US';
    u.rate = 1.0;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  }}

  speakBtn.addEventListener('click', speak);
  stopBtn.addEventListener('click', stopSpeaking);

  if (cfg.autoplay) {{
    // Some browsers require a short delay after iframe load before speak() works.
    setTimeout(speak, 120);
  }}
}})();
</script>
</body>
</html>
"""
