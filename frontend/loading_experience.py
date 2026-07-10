# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/loading_experience.py
------------------------------
Module #31 — State-aware progress UI for live agent transitions (Streamlit).

Subscribes to GET /chat/stream/{session_id} (Module #30) while POST /chat runs.
Uses Streamlit ``st.empty()`` placeholders for incremental rerenders — the only
UI framework in ``frontend/`` is Streamlit (``streamlit_app.py``).
"""
from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

try:
    import api_client
except ImportError:  # pytest / package import from repo root
    from frontend import api_client as api_client

# Fixed step order — seven backend states before RESPOND (matches Module #30).
TOTAL_STEPS = 7
STEP_ORDER: tuple[str, ...] = (
    "INTAKE",
    "PLAN",
    "ACT",
    "OBSERVE",
    "DECIDE",
    "FINALIZE",
    "VERIFY",
)

# Icons per state (labels come verbatim from SSE — mirrored here only for step-1 bootstrap).
STATE_ICONS: dict[str, str] = {
    "INTAKE": "💬",
    "PLAN": "🧭",
    "ACT": "🔍",
    "OBSERVE": "📋",
    "DECIDE": "⚖️",
    "FINALIZE": "✍️",
    "VERIFY": "🛡️",
    "RESPOND": "✅",
}

# Bootstrap label — must match Module #30 STATE_LABELS["INTAKE"] (no backend import).
_BOOTSTRAP_STATE = "INTAKE"
_BOOTSTRAP_LABEL = "Understanding your question…"

# Stream-drop / stall fallback before RESPOND.
STREAM_STALL_TIMEOUT_S = 15.0
STILL_WORKING_LABEL = "Still working…"

def _skeleton_css() -> str:
    """Loading UI styles from Module #34 theme tokens (no hardcoded palette)."""
    try:
        from theme import widget_style_tokens
    except ImportError:
        from frontend.theme import widget_style_tokens

    t = widget_style_tokens()
    return f"""
<style>
@keyframes le-shimmer {{
  0% {{ background-position: -200px 0; }}
  100% {{ background-position: calc(200px + 100%) 0; }}
}}
.le-progress {{
  font-size: 0.95rem;
  font-weight: 600;
  color: {t["text"]};
  margin-bottom: 0.35rem;
  font-family: {t["font_family"]};
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}}
.le-step-badge {{
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: {t["accent_strong"]};
  color: {t["text_inverse"]};
}}
.le-progress .le-icon {{
  display: inline-block;
  animation: le-pulse 1.4s ease-in-out infinite;
}}
@keyframes le-pulse {{
  0%, 100% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: 0.65; transform: scale(0.96); }}
}}
.le-skeleton .le-line {{
  height: 12px;
  border-radius: 6px;
  margin: 10px 0;
  background: linear-gradient(90deg, {t["skeleton_a"]} 0px, {t["skeleton_b"]} 40px, {t["skeleton_a"]} 80px);
  background-size: 200px 100%;
  animation: le-shimmer 1.3s ease-in-out infinite;
}}
</style>
"""


def _step_number(state: str) -> int | None:
    if state in STEP_ORDER:
        return STEP_ORDER.index(state) + 1
    if state == "RESPOND":
        return TOTAL_STEPS
    return None


def render_state(placeholder: Any, state: str, label: str) -> None:
    """Map backend ``{state, label}`` to a step line + icon in the Streamlit placeholder."""
    icon = STATE_ICONS.get(state, "⏳")
    step = _step_number(state)
    if step is not None and state != "RESPOND":
        badge = f"<span class='le-step-badge'>{step}/{TOTAL_STEPS}</span>"
        line = f"{badge}<span class='le-icon'>{icon}</span> {label}"
    elif state == "RESPOND":
        line = f"<span class='le-icon'>{icon}</span> {label}"
    else:
        line = f"<span class='le-icon'>{icon}</span> {label}"
    placeholder.markdown(f"{_skeleton_css()}<div class='le-progress'>{line}</div>", unsafe_allow_html=True)


def render_skeleton(placeholder: Any) -> None:
    """Grey animated placeholder lines — active only during FINALIZE."""
    placeholder.markdown(
        f"""{_skeleton_css()}
<div class="le-skeleton">
  <div class="le-line" style="width:96%"></div>
  <div class="le-line" style="width:88%"></div>
  <div class="le-line" style="width:74%"></div>
  <div class="le-line" style="width:62%"></div>
</div>""",
        unsafe_allow_html=True,
    )


def _parse_sse_data_line(line: str) -> dict[str, Any] | None:
    if not line or not line.startswith("data: "):
        return None
    try:
        payload = json.loads(line[6:].strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if "state" not in payload or "label" not in payload or "timestamp" not in payload:
        return None
    return payload


def iter_sse_events(session_id: str) -> Iterator[dict[str, Any]]:
    """Blocking iterator over GET /chat/stream/{session_id} SSE frames."""
    url = f"{api_client.API_BASE_URL}/chat/stream/{session_id}"
    with requests.get(
        url,
        headers=api_client._get_headers(),
        stream=True,
        timeout=(10, 320),
    ) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            event = _parse_sse_data_line(raw)
            if event is not None:
                yield event
                if event.get("state") == "RESPOND":
                    return


def run_chat_with_loading(
    progress_placeholder: Any,
    skeleton_placeholder: Any,
    *,
    session_id: str,
    repo_id: str,
    question: str,
    chat_callable: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """
    Open SSE, show step 1 immediately, poll events while POST /chat runs.

    Final answer is detected when ``chat_callable`` returns (POST /chat resolved).
    The skeleton shown during FINALIZE is cleared by the caller before rendering
    the real answer + citations — no double-render.
    """
    event_q: queue.Queue[tuple[str, Any]] = queue.Queue()
    result_box: dict[str, Any] = {}
    error_box: dict[str, Exception] = {}

    def _sse_worker() -> None:
        try:
            for evt in iter_sse_events(session_id):
                event_q.put(("event", evt))
        except Exception as exc:
            event_q.put(("sse_error", exc))
        finally:
            event_q.put(("sse_closed", None))

    def _chat_worker() -> None:
        try:
            result_box["response"] = chat_callable(
                repo_id, question, session_id=session_id
            )
        except Exception as exc:
            error_box["error"] = exc
        finally:
            event_q.put(("chat_done", None))

    render_state(progress_placeholder, _BOOTSTRAP_STATE, _BOOTSTRAP_LABEL)
    skeleton_placeholder.empty()

    threading.Thread(target=_sse_worker, name=f"sse-{session_id[:8]}", daemon=True).start()
    threading.Thread(target=_chat_worker, name=f"chat-{session_id[:8]}", daemon=True).start()

    current_state = _BOOTSTRAP_STATE
    showing_skeleton = False
    respond_seen = False
    chat_done = False
    last_progress_at = time.monotonic()
    stall_shown = False

    while not chat_done:
        try:
            kind, payload = event_q.get(timeout=0.25)
        except queue.Empty:
            if (
                not respond_seen
                and not chat_done
                and not stall_shown
                and (time.monotonic() - last_progress_at) >= STREAM_STALL_TIMEOUT_S
            ):
                render_state(progress_placeholder, current_state, STILL_WORKING_LABEL)
                stall_shown = True
            continue

        if kind == "event":
            evt = payload
            state = evt["state"]
            label = evt["label"]
            current_state = state
            last_progress_at = time.monotonic()
            stall_shown = False

            if state == "FINALIZE":
                render_state(progress_placeholder, state, label)
                render_skeleton(skeleton_placeholder)
                showing_skeleton = True
            elif state == "RESPOND":
                respond_seen = True
                render_state(progress_placeholder, state, label)
            else:
                if showing_skeleton:
                    skeleton_placeholder.empty()
                    showing_skeleton = False
                render_state(progress_placeholder, state, label)

        elif kind == "chat_done":
            chat_done = True
        elif kind == "sse_closed" and not respond_seen and not stall_shown:
            if (time.monotonic() - last_progress_at) >= STREAM_STALL_TIMEOUT_S:
                render_state(progress_placeholder, current_state, STILL_WORKING_LABEL)
                stall_shown = True

    if "error" in error_box:
        progress_placeholder.empty()
        skeleton_placeholder.empty()
        raise error_box["error"]

    return result_box["response"]
