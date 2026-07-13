# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #33 — browser SpeechSynthesis TTS helpers."""
from __future__ import annotations

import re
from pathlib import Path

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:  # pragma: no cover
    st = None  # type: ignore
    components = None  # type: ignore

VOICE_OUTPUT_SESSION_KEY = "voice_output_enabled"

_BACKTICK_CITE = re.compile(
    r"`((?:[\w./\\\-@]+/)?[\w.\-]+\.[\w]{1,12}):(\d+)(?:-(\d+))?`",
    re.IGNORECASE,
)
_BARE_CITE = re.compile(
    r"(?<![`\w])((?:[\w./\\\-@]+/)?[\w.\-]+\.[\w]{1,12}):(\d+)(?:-(\d+))?(?![`\w:])",
    re.IGNORECASE,
)


def _basename(path: str) -> str:
    return Path(path.replace("\\", "/")).name


def strip_for_speech(text: str) -> str:
    """Strip markdown/citations for natural TTS."""
    if not text:
        return ""

    out = text
    out = re.sub(r"```[\s\S]*?```", "", out)
    out = re.sub(r"`([^`]+)`", _cite_repl, out)
    out = _BARE_CITE.sub(_bare_cite_repl, out)
    out = re.sub(r"^#{1,6}\s+", "", out, flags=re.MULTILINE)
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"\*([^*]+)\*", r"\1", out)
    out = re.sub(r"^\s*[-*]\s+", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*\d+\.\s+", "", out, flags=re.MULTILINE)
    out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _cite_repl(match: re.Match[str]) -> str:
    return f" according to {_basename(match.group(1))} "


def _bare_cite_repl(match: re.Match[str]) -> str:
    return f" according to {_basename(match.group(1))} "


def is_voice_output_enabled() -> bool:
    if st is None:
        return False
    return bool(st.session_state.get(VOICE_OUTPUT_SESSION_KEY, False))


def toggle_voice_output(enabled: bool) -> None:
    if st is None:
        return
    st.session_state[VOICE_OUTPUT_SESSION_KEY] = bool(enabled)


def _tts_widget_html(text: str, *, language: str = "en-US", autoplay: bool = False) -> str:
    safe = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    auto = "true" if autoplay else "false"
    return f"""
<script>
(function() {{
  if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {{
    document.body.setAttribute('data-tts-unsupported', 'true');
    return;
  }}
  window.speechSynthesis.cancel();
  var u = new SpeechSynthesisUtterance('{safe}');
  u.lang = '{language}';
  if ({auto}) window.speechSynthesis.speak(u);
}})();
</script>
<p class="cn-tts unsupported" style="display:none">TTS unsupported in this browser.</p>
""".strip()


def speak(answer_text: str, language: str = "en-US") -> None:
    cleaned = strip_for_speech(answer_text)
    if not cleaned.strip():
        return None
    if components is None:
        return None
    components.html(_tts_widget_html(cleaned, language=language, autoplay=True), height=0)
    return None
