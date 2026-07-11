# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/loading_experience.py
------------------------------
Module #31 — State-aware progress UI for live agent transitions (Streamlit).

Implementation choice: **(a) st.empty() + SSE polling loop** (not a custom JS iframe).

Why: The app already uses Streamlit placeholders + ``GET /chat/stream/{session_id}``
(Module #30). Polling SSE from a background thread and updating ``st.empty()``
every ~250ms reuses existing auth headers, avoids iframe height clipping, and
keeps the loading UI in the same design-token CSS as Module #34 — with zero added
backend latency (purely perceptual).
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

# Short labels on the horizontal stepper segments.
STEP_SHORT_LABELS: dict[str, str] = {
    "INTAKE": "Receive",
    "PLAN": "Understand",
    "ACT": "Search",
    "OBSERVE": "Read",
    "DECIDE": "Reason",
    "FINALIZE": "Write",
    "VERIFY": "Verify",
}

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

_BOOTSTRAP_STATE = "INTAKE"
_BOOTSTRAP_LABEL = "Preparing your request…"

STREAM_STALL_TIMEOUT_S = 15.0
MICRO_COPY_ROTATE_S = 5.0
STILL_WORKING_LABEL = "Still working…"

STATE_MICRO_COPY: dict[str, list[str]] = {
    "INTAKE": ["Understanding what you need…", "Getting context ready…"],
    "PLAN": ["Understanding your question…", "Choosing the best search strategy…"],
    "ACT": ["Searching the codebase…", "Scanning indexed files…"],
    "OBSERVE": ["Reading relevant code…", "Gathering the strongest evidence…"],
    "DECIDE": [
        "Reasoning about the answer…",
        "Checking if we have enough context…",
        "Weighing retrieved evidence…",
    ],
    "FINALIZE": [
        "Writing the response…",
        "Still generating a grounded answer…",
        "Almost there…",
    ],
    "VERIFY": [
        "Double-checking citations…",
        "Verifying claims against source code…",
        "Ensuring every citation is grounded…",
    ],
    "RESPOND": ["Finalizing…", "Delivering your answer…"],
}

_DEFAULT_MICRO_COPY = [
    STILL_WORKING_LABEL,
    "Hang tight — the agent is still working…",
    "Almost there…",
]


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
@keyframes le-pulse-glow {{
  0%, 100% {{
    opacity: 1;
    box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.45);
  }}
  50% {{
    opacity: 0.92;
    box-shadow: 0 0 0 6px rgba(99, 102, 241, 0.12);
  }}
}}
.le-wrap {{
  font-family: {t["font_family"]};
  color: {t["text"]};
  margin-bottom: 0.5rem;
}}
.le-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.65rem;
  flex-wrap: wrap;
}}
.le-elapsed {{
  font-size: 0.72rem;
  font-weight: 600;
  color: {t["text_muted"]};
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
}}
.le-stepper {{
  display: flex;
  gap: 0.2rem;
  margin-bottom: 0.55rem;
}}
.le-seg {{
  flex: 1;
  min-width: 0;
  text-align: center;
  font-size: 0.58rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: {t["text_muted"]};
  opacity: 0.55;
  transition: color 0.2s ease, opacity 0.2s ease;
}}
.le-seg-bar {{
  height: 4px;
  border-radius: 999px;
  background: {t["skeleton_a"]};
  margin: 0.28rem 0 0.22rem;
  position: relative;
  overflow: hidden;
}}
.le-seg.done {{
  opacity: 1;
  color: {t["success_fg"]};
}}
.le-seg.done .le-seg-bar {{
  background: {t["success_fg"]};
}}
.le-seg.done .le-seg-bar::after {{
  content: "✓";
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.5rem;
  color: {t["text_inverse"]};
  line-height: 1;
}}
.le-seg.active {{
  opacity: 1;
  color: {t["accent_strong"]};
}}
.le-seg.active .le-seg-bar {{
  background: {t["accent_strong"]};
  animation: le-pulse-glow 1.5s ease-in-out infinite;
}}
.le-seg.future .le-seg-bar {{
  background: {t["skeleton_a"]};
}}
.le-current {{
  display: flex;
  align-items: flex-start;
  gap: 0.45rem;
  font-size: 0.92rem;
  font-weight: 600;
  color: {t["text"]};
  line-height: 1.35;
  margin-bottom: 0.2rem;
}}
.le-current .le-icon {{
  flex-shrink: 0;
  animation: le-icon-pulse 1.4s ease-in-out infinite;
}}
@keyframes le-icon-pulse {{
  0%, 100% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: 0.7; transform: scale(0.96); }}
}}
.le-micro {{
  font-size: 0.8rem;
  font-weight: 500;
  color: {t["text_muted"]};
  margin-top: 0.1rem;
  min-height: 1.2em;
}}
.le-skeleton .le-line {{
  height: 12px;
  border-radius: 6px;
  margin: 10px 0;
  background: linear-gradient(90deg, {t["skeleton_a"]} 0px, {t["skeleton_b"]} 40px, {t["skeleton_a"]} 80px);
  background-size: 200px 100%;
  animation: le-shimmer 1.6s ease-in-out infinite;
}}
</style>
"""


def _step_number(state: str) -> int | None:
    if state in STEP_ORDER:
        return STEP_ORDER.index(state) + 1
    if state == "RESPOND":
        return TOTAL_STEPS
    return None


def _stepper_html(current_state: str) -> str:
    """Horizontal 7-segment stepper — done ✓, active pulse, future muted."""
    active_idx = STEP_ORDER.index(current_state) if current_state in STEP_ORDER else 0
    if current_state == "RESPOND":
        active_idx = len(STEP_ORDER)

    parts = ['<div class="le-stepper">']
    for i, state in enumerate(STEP_ORDER):
        if i < active_idx or current_state == "RESPOND":
            cls = "le-seg done"
        elif i == active_idx:
            cls = "le-seg active"
        else:
            cls = "le-seg future"
        short = STEP_SHORT_LABELS.get(state, state[:4])
        parts.append(
            f'<div class="{cls}"><div class="le-seg-bar"></div>{short}</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _micro_copy_for(state: str, elapsed_in_state_s: float) -> str:
    pool = STATE_MICRO_COPY.get(state) or _DEFAULT_MICRO_COPY
    if elapsed_in_state_s < MICRO_COPY_ROTATE_S:
        return pool[0]
    idx = int(elapsed_in_state_s // MICRO_COPY_ROTATE_S) % len(pool)
    return pool[idx]


def render_progress_panel(
    placeholder: Any,
    state: str,
    label: str,
    *,
    elapsed_s: float = 0.0,
    micro_copy: str = "",
) -> None:
    """Live stepper + current label + optional micro-copy + elapsed timer."""
    icon = STATE_ICONS.get(state, "⏳")
    step = _step_number(state)
    badge = ""
    if step is not None and state != "RESPOND":
        badge = f"<span style='font-size:0.7rem;opacity:0.75;margin-right:0.25rem'>{step}/{TOTAL_STEPS}</span>"

    micro_line = f'<div class="le-micro">{micro_copy}</div>' if micro_copy else ""
    elapsed_label = f"{max(0, int(elapsed_s))}s elapsed"

    html = f"""{_skeleton_css()}
<div class="le-wrap">
  <div class="le-header">
    <span style="font-size:0.72rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;opacity:0.7">Agent progress</span>
    <span class="le-elapsed">{elapsed_label}</span>
  </div>
  {_stepper_html(state)}
  <div class="le-current">{badge}<span class="le-icon">{icon}</span><span>{label}</span></div>
  {micro_line}
</div>"""
    placeholder.markdown(html, unsafe_allow_html=True)


def render_state(placeholder: Any, state: str, label: str) -> None:
    """Backward-compatible wrapper — renders full progress panel."""
    render_progress_panel(placeholder, state, label)


def render_skeleton(placeholder: Any) -> None:
    """Shimmer skeleton lines for the incoming answer body."""
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

    Updates the progress placeholder on each SSE frame and every poll tick
    (elapsed timer + micro-copy rotation) — no extra backend calls.
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

    started_at = time.monotonic()
    state_entered_at = started_at
    current_state = _BOOTSTRAP_STATE
    current_label = _BOOTSTRAP_LABEL

    render_progress_panel(
        progress_placeholder,
        current_state,
        current_label,
        elapsed_s=0.0,
        micro_copy=_micro_copy_for(current_state, 0.0),
    )
    skeleton_placeholder.empty()

    threading.Thread(target=_sse_worker, name=f"sse-{session_id[:8]}", daemon=True).start()
    threading.Thread(target=_chat_worker, name=f"chat-{session_id[:8]}", daemon=True).start()

    showing_skeleton = False
    respond_seen = False
    chat_done = False
    last_progress_at = started_at

    while not chat_done:
        now = time.monotonic()
        elapsed_total = now - started_at
        elapsed_in_state = now - state_entered_at

        micro = _micro_copy_for(current_state, elapsed_in_state)
        if (
            not respond_seen
            and (now - last_progress_at) >= STREAM_STALL_TIMEOUT_S
        ):
            micro = _micro_copy_for(current_state, elapsed_in_state + MICRO_COPY_ROTATE_S)

        render_progress_panel(
            progress_placeholder,
            current_state,
            current_label,
            elapsed_s=elapsed_total,
            micro_copy=micro,
        )

        try:
            kind, payload = event_q.get(timeout=0.25)
        except queue.Empty:
            continue

        if kind == "event":
            evt = payload
            state = evt["state"]
            label = evt["label"]
            if state != current_state:
                current_state = state
                current_label = label
                state_entered_at = time.monotonic()
            else:
                current_label = label
            last_progress_at = time.monotonic()

            if state == "FINALIZE":
                render_skeleton(skeleton_placeholder)
                showing_skeleton = True
            elif state == "RESPOND":
                respond_seen = True
            else:
                if showing_skeleton:
                    skeleton_placeholder.empty()
                    showing_skeleton = False

        elif kind == "chat_done":
            chat_done = True
        elif kind == "sse_closed" and not respond_seen:
            pass

    if "error" in error_box:
        progress_placeholder.empty()
        skeleton_placeholder.empty()
        raise error_box["error"]

    return result_box["response"]
