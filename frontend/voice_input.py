# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/voice_input.py
-----------------------
Module #32 — Browser-native voice-to-text for chat (Web Speech API).

Audio stays in the browser; only plain text is returned to Streamlit for the
existing ``POST /chat`` path. Implemented for Streamlit via ``components.html``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import streamlit as st
import streamlit.components.v1 as components

# Auto-submit after this much silence once the user stops speaking (milliseconds).
AUTO_SUBMIT_PAUSE_MS = 1500

# Fixed shortcut phrases → existing UI actions (checked before /chat).
VOICE_SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("explain again", "explain_again"),
    ("ask again", "explain_again"),
    ("repeat that", "explain_again"),
    ("show diagram", "show_diagram"),
    ("generate diagram", "show_diagram"),
)

VoiceAction = Literal["explain_again", "show_diagram"]
VoiceKind = Literal["normal_question", "shortcut"]


@dataclass(frozen=True)
class VoiceCommand:
    kind: VoiceKind
    text: str
    action: VoiceAction | None = None
    symbol: str | None = None


def _normalize_transcript(text: str) -> str:
    return " ".join(text.lower().strip().split())


def parse_voice_command(text: str) -> VoiceCommand:
    """
    Match shortcut phrases deterministically before treating text as a new question.

    Shortcut map:
    - ``explain again`` / ``ask again`` / ``repeat that`` → ``explain_again``
    - ``show diagram`` / ``generate diagram`` → ``show_diagram`` (optional symbol tail)
    """
    raw = text.strip()
    norm = _normalize_transcript(raw)

    for phrase, action in VOICE_SHORTCUTS:
        if norm == phrase or norm.startswith(f"{phrase} "):
            symbol: str | None = None
            if norm.startswith(f"{phrase} "):
                tail_raw = raw[len(phrase) :].strip()
                tail_lower = tail_raw.lower()
                if tail_lower.startswith("for "):
                    symbol = tail_raw[4:].strip() or None
                elif tail_lower.startswith("of "):
                    symbol = tail_raw[3:].strip() or None
                else:
                    symbol = tail_raw or None
            return VoiceCommand(
                kind="shortcut",
                text=raw,
                action=action,  # type: ignore[arg-type]
                symbol=symbol,
            )

    return VoiceCommand(kind="normal_question", text=raw)


def on_transcript_final(text: str) -> dict[str, Any]:
    """
    Prepare a voice submission after speech ends.

    The browser widget fills an editable textarea and starts an
    ``AUTO_SUBMIT_PAUSE_MS`` timer; the user may edit or cancel before submit.
    """
    cmd = parse_voice_command(text)
    return {
        "text": cmd.text,
        "command": cmd,
        "auto_submit_pause_ms": AUTO_SUBMIT_PAUSE_MS,
    }


def resolve_voice_submission(
    text: str,
    chat_history: list[dict[str, Any]],
    *,
    last_diagram_symbol: str | None = None,
) -> dict[str, Any]:
    """
    Turn final transcript text into an action for ``streamlit_app.py``.

    Returns one of:
    - ``{"route": "chat", "question": str}``
    - ``{"route": "explain_again", "question": str}``
    - ``{"route": "diagram", "symbol": str}``
    """
    cmd = parse_voice_command(text)

    if cmd.kind == "shortcut" and cmd.action == "explain_again":
        prior = _last_user_question(chat_history)
        if prior:
            return {"route": "explain_again", "question": prior}
        return {"route": "chat", "question": cmd.text}

    if cmd.kind == "shortcut" and cmd.action == "show_diagram":
        symbol = cmd.symbol or last_diagram_symbol
        if symbol:
            return {"route": "diagram", "symbol": symbol}
        return {
            "route": "chat",
            "question": "Which symbol should I diagram? Say e.g. show diagram for Session.send",
        }

    return {"route": "chat", "question": cmd.text}


def _last_user_question(chat_history: list[dict[str, Any]]) -> str | None:
    for msg in reversed(chat_history):
        if msg.get("role") == "user" and msg.get("content"):
            return str(msg["content"])
    return None


def _decode_voice_payload(raw: str) -> dict[str, Any] | None:
    """Decode base64url JSON (preferred) or plain JSON (legacy)."""
    import base64

    text = (raw or "").strip()
    if not text:
        return None

    candidates: list[str] = [text]
    # base64url → std base64 padding
    padded = text + ("=" * (-len(text) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        candidates.insert(0, decoded)
    except Exception:
        pass

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {"error": "invalid_payload"}


def drain_browser_voice_event() -> dict[str, Any] | None:
    """
    Read a one-shot payload from the browser voice widget.

    Transport: compact base64url ``vi_payload`` query param (Streamlit
    ``components.html`` is one-way — query params are the reliable bridge).
    Cleared after read so refresh cannot replay the event.
    """
    raw = st.query_params.get("vi_payload")
    if not raw:
        return None
    try:
        del st.query_params["vi_payload"]
    except Exception:
        pass
    return _decode_voice_payload(raw if isinstance(raw, str) else str(raw))


def apply_browser_voice_event(
    event: dict[str, Any],
    chat_history: list[dict[str, Any]],
    *,
    last_diagram_symbol: str | None = None,
) -> dict[str, Any] | None:
    """
    Apply browser event to session state.

    Handles permission denial messages and final transcript submissions.
    """
    if event.get("type") == "permission_denied":
        st.session_state.voice_permission_denied = True
        return None

    if event.get("type") != "submit" or not event.get("text"):
        return None

    st.session_state.voice_permission_denied = False
    return resolve_voice_submission(
        str(event["text"]),
        chat_history,
        last_diagram_symbol=last_diagram_symbol,
    )


def render_permission_notice() -> None:
    if st.session_state.get("voice_permission_denied"):
        st.caption("Microphone access was denied — type your question below.")


def render_voice_input(*, disabled: bool = False, component_key: str = "voice_input") -> None:
    """
    Mount mic control + live waveform next to chat.

    ``start_listening()`` runs in embedded JS (``SpeechRecognition`` /
    ``webkitSpeechRecognition``). Unsupported browsers hide the widget at load.
    """
    del component_key  # reserved for future custom bidirectional component
    components.html(
        _voice_widget_html(disabled=disabled, auto_submit_ms=AUTO_SUBMIT_PAUSE_MS),
        height=148,
        scrolling=False,
    )


def _voice_widget_html(*, disabled: bool, auto_submit_ms: int) -> str:
    disabled_attr = "true" if disabled else "false"
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
  body {{ margin: 0; padding: 6px 4px; background: transparent; }}
  #voice-root {{ display: flex; align-items: flex-start; gap: 10px; }}
  #voice-root.unsupported {{ display: none !important; }}
  #mic-btn {{
    width: 44px; height: 44px; border-radius: 50%; border: none; cursor: pointer;
    background: linear-gradient(135deg, {t["blue_500"]}, {t["teal_400"]}); color: {t["text_inverse"]}; font-size: 18px;
    flex-shrink: 0; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35);
  }}
  #mic-btn:disabled {{ opacity: .45; cursor: not-allowed; }}
  #mic-btn.listening {{ animation: pulse 1.2s ease-in-out infinite; background: {t["danger"]}; }}
  @keyframes pulse {{ 0%,100%{{transform:scale(1)}} 50%{{transform:scale(1.06)}} }}
  .panel {{ flex: 1; min-width: 0; }}
  #wave-wrap {{
    height: 36px; display: none; align-items: flex-end; gap: 3px; margin-bottom: 6px;
  }}
  #wave-wrap.active {{ display: flex; }}
  .bar {{
    width: 4px; background: {t["accent"]}; border-radius: 2px; height: 8px;
    transition: height 0.08s ease;
  }}
  #transcript {{
    width: 100%; min-height: 38px; resize: vertical; border: 1px solid {t["border"]};
    border-radius: 8px; padding: 8px 10px; font-size: 0.9rem; display: none;
    background: {t["surface"]}; color: {t["text"]};
  }}
  #transcript.visible {{ display: block; }}
  #perm-msg {{ color: {t["warning_fg"]}; font-size: 0.82rem; margin: 4px 0 0; display: none; }}
  #perm-msg.show {{ display: block; }}
  .actions {{ margin-top: 6px; display: none; gap: 8px; }}
  .actions.visible {{ display: flex; }}
  .actions button {{
    border: none; border-radius: 6px; padding: 6px 12px; font-size: 0.82rem; cursor: pointer;
  }}
  #send-btn {{ background: {t["accent_strong"]}; color: {t["text_inverse"]}; }}
  #cancel-btn {{ background: {t["skeleton_b"]}; color: {t["text"]}; }}
</style>
</head>
<body>
<div id="voice-root">
  <button id="mic-btn" title="Voice input" {'disabled' if disabled else ''}>🎤</button>
  <div class="panel">
    <div id="wave-wrap" aria-hidden="true"></div>
    <textarea id="transcript" rows="2" placeholder="Speak, then edit if needed…"></textarea>
    <div id="perm-msg">Microphone access was denied — type your question below.</div>
    <div class="actions" id="actions">
      <button id="send-btn" type="button">Send</button>
      <button id="cancel-btn" type="button">Cancel</button>
    </div>
  </div>
</div>
<script>
(function() {{
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const root = document.getElementById('voice-root');
  const micBtn = document.getElementById('mic-btn');
  const waveWrap = document.getElementById('wave-wrap');
  const transcript = document.getElementById('transcript');
  const permMsg = document.getElementById('perm-msg');
  const actions = document.getElementById('actions');
  const sendBtn = document.getElementById('send-btn');
  const cancelBtn = document.getElementById('cancel-btn');
  const disabled = {disabled_attr};
  const AUTO_MS = {auto_submit_ms};
  const MIC_KEY = 'cn_voice_mic_granted';

  if (!SpeechRecognition) {{
    root.classList.add('unsupported');
    return;
  }}

  // Build waveform bars
  const bars = [];
  for (let i = 0; i < 24; i++) {{
    const b = document.createElement('div');
    b.className = 'bar';
    waveWrap.appendChild(b);
    bars.push(b);
  }}

  let recognition = null;
  let micStream = null;
  let audioCtx = null;
  let analyser = null;
  let rafId = null;
  let autoTimer = null;
  let listening = false;

  function toBase64Url(obj) {{
    const json = JSON.stringify(obj);
    const bytes = new TextEncoder().encode(json);
    let bin = '';
    bytes.forEach((b) => {{ bin += String.fromCharCode(b); }});
    return btoa(bin).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/g, '');
  }}

  function postEvent(payload) {{
    // Compact base64url query bridge — safe for special chars / unicode.
    // Streamlit components.html is one-way; query params are the reliable path.
    try {{
      const text = (payload && payload.text) ? String(payload.text) : '';
      if (text.length > 1200) {{
        payload = Object.assign({{}}, payload, {{ text: text.slice(0, 1200) }});
      }}
      const encoded = toBase64Url(payload);
      const topWin = window.top || window.parent || window;
      const url = new URL(topWin.location.href);
      url.searchParams.set('vi_payload', encoded);
      topWin.location.assign(url.toString());
    }} catch (err) {{
      console.error('voice_input postEvent failed', err);
    }}
  }}

  function clearAutoTimer() {{
    if (autoTimer) {{ clearTimeout(autoTimer); autoTimer = null; }}
  }}

  function scheduleAutoSubmit() {{
    clearAutoTimer();
    autoTimer = setTimeout(() => {{
      const text = transcript.value.trim();
      if (text) submitTranscript(text);
    }}, AUTO_MS);
  }}

  function submitTranscript(text) {{
    clearAutoTimer();
    stopListening();
    postEvent({{ type: 'submit', text: text }});
  }}

  function showTranscript(text) {{
    transcript.classList.add('visible');
    actions.classList.add('visible');
    if (typeof text === 'string') transcript.value = text;
  }}

  function animateWave() {{
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    const step = Math.floor(data.length / bars.length);
    bars.forEach((bar, i) => {{
      const v = data[i * step] || 0;
      bar.style.height = Math.max(6, (v / 255) * 34) + 'px';
    }});
    rafId = requestAnimationFrame(animateWave);
  }}

  async function ensureMicStream() {{
    if (micStream) return micStream;
    micStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
    sessionStorage.setItem(MIC_KEY, '1');
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(micStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    source.connect(analyser);
    return micStream;
  }}

  function stopWave() {{
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    waveWrap.classList.remove('active');
    bars.forEach(b => {{ b.style.height = '8px'; }});
  }}

  function stopListening() {{
    listening = false;
    micBtn.classList.remove('listening');
    stopWave();
    try {{ if (recognition) recognition.stop(); }} catch (e) {{}}
  }}

  function start_listening() {{
    if (disabled || listening) return;
    permMsg.classList.remove('show');
    recognition = new SpeechRecognition();
    recognition.lang = navigator.language || 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;

    recognition.onresult = (event) => {{
      let interim = '';
      let finalText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {{
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += piece;
        else interim += piece;
      }}
      const live = (transcript.value.split('\\n').pop() || '');
      const combined = finalText || interim || live;
      showTranscript(finalText ? (transcript.value.replace(/\\s*$/, '') + ' ' + finalText).trim() : (interim || transcript.value));
      if (finalText.trim()) scheduleAutoSubmit();
    }};

    recognition.onerror = (event) => {{
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {{
        permMsg.classList.add('show');
        sessionStorage.removeItem(MIC_KEY);
        postEvent({{ type: 'permission_denied' }});
      }}
      stopListening();
    }};

    recognition.onend = () => {{
      if (listening) {{
        try {{ recognition.start(); }} catch (e) {{ listening = false; }}
      }} else {{
        micBtn.classList.remove('listening');
        stopWave();
      }}
    }};

    ensureMicStream().then(() => {{
      listening = true;
      micBtn.classList.add('listening');
      waveWrap.classList.add('active');
      animateWave();
      recognition.start();
      showTranscript('');
    }}).catch(() => {{
      permMsg.classList.add('show');
      postEvent({{ type: 'permission_denied' }});
    }});
  }}

  micBtn.addEventListener('click', start_listening);
  sendBtn.addEventListener('click', () => {{
    const text = transcript.value.trim();
    if (text) submitTranscript(text);
  }});
  cancelBtn.addEventListener('click', () => {{
    clearAutoTimer();
    stopListening();
    transcript.value = '';
    transcript.classList.remove('visible');
    actions.classList.remove('visible');
  }});
  transcript.addEventListener('input', () => clearAutoTimer());
}})();
</script>
</body>
</html>
"""


# Browser ``start_listening()`` is embedded in ``_voice_widget_html`` above.
