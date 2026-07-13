# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #32 — Web Speech voice input helpers."""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore

AUTO_SUBMIT_PAUSE_MS = 1200

VOICE_SHORTCUTS: list[tuple[str, str]] = [
    ("explain again", "explain_again"),
    ("ask again", "explain_again"),
    ("repeat that", "explain_again"),
    ("show diagram", "show_diagram"),
    ("generate diagram", "show_diagram"),
]


@dataclass
class VoiceCommand:
    kind: str  # "normal_question" | "shortcut"
    text: str
    action: str | None = None
    symbol: str | None = None


def parse_voice_command(text: str) -> VoiceCommand:
    normalized = text.strip().lower()
    for phrase, action in VOICE_SHORTCUTS:
        if normalized == phrase or normalized.startswith(phrase + " "):
            symbol = None
            if action == "show_diagram":
                m = re.search(r"\bfor\s+(.+)$", text.strip(), re.I)
                if m:
                    symbol = m.group(1).strip()
            return VoiceCommand(kind="shortcut", text=text.strip(), action=action, symbol=symbol)
    return VoiceCommand(kind="normal_question", text=text.strip(), action=None)


def resolve_voice_submission(
    text: str,
    history: list[dict[str, Any]],
    *,
    last_diagram_symbol: str | None = None,
) -> dict[str, Any]:
    cmd = parse_voice_command(text)
    if cmd.kind == "shortcut" and cmd.action == "explain_again":
        for msg in reversed(history):
            if msg.get("role") == "user" and msg.get("content"):
                return {"route": "explain_again", "question": str(msg["content"])}
        return {"route": "explain_again", "question": text}
    if cmd.kind == "shortcut" and cmd.action == "show_diagram":
        symbol = cmd.symbol or last_diagram_symbol
        return {"route": "diagram", "symbol": symbol}
    return {"route": "chat", "question": cmd.text}


def on_transcript_final(text: str) -> dict[str, Any]:
    return {"text": text.strip(), "auto_submit_pause_ms": AUTO_SUBMIT_PAUSE_MS}


def _decode_voice_payload(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None


def apply_browser_voice_event(event: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any] | None:
    if event.get("type") == "permission_denied":
        if st is not None:
            st.session_state.voice_permission_denied = True
        return None
    if event.get("type") == "submit" and event.get("text"):
        return resolve_voice_submission(str(event["text"]), history)
    return None


def _voice_widget_html(*, disabled: bool, auto_submit_ms: int) -> str:
    dis = "true" if disabled else "false"
    return f"""
<script>
(function() {{
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{
    document.body.setAttribute('data-voice-unsupported', 'unsupported');
    return;
  }}
  function toBase64Url(str) {{
    return btoa(unescape(encodeURIComponent(str))).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
  }}
  var ctx = new (window.AudioContext || window.webkitAudioContext)();
  var analyser = ctx.createAnalyser();
  var vi_payload = toBase64Url(JSON.stringify({{type:'ready'}}));
  window.__cn_voice_auto_submit_ms = {auto_submit_ms};
  window.__cn_voice_disabled = {dis};
}})();
</script>
<p class="cn-voice unsupported">Voice unsupported in this browser.</p>
""".strip()
