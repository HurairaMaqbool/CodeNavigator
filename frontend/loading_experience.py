# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #31 — state-aware loading / SSE progress UI."""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Iterator

import requests

MICRO_COPY_ROTATE_S = 5.0
STREAM_STALL_TIMEOUT_S = 30.0
TOTAL_STEPS = 7

STEP_ORDER = ["INTAKE", "PLAN", "ACT", "OBSERVE", "DECIDE", "FINALIZE", "VERIFY"]

STATE_ICONS = {
    "INTAKE": "📥",
    "PLAN": "🧭",
    "ACT": "🔍",
    "OBSERVE": "👁",
    "DECIDE": "⚖",
    "FINALIZE": "✍",
    "VERIFY": "🛡",
    "RESPOND": "✅",
}

_STEP_LABELS = ["Prepare", "Plan", "Search", "Review", "Decide", "Write", "Verify"]

_MICRO_COPY: dict[str, list[str]] = {
    "PLAN": [
        "Understanding your question…",
        "Choosing the best search strategy…",
    ],
    "ACT": [
        "Searching the codebase…",
        "Scanning indexed files…",
    ],
    "FINALIZE": [
        "Writing the response…",
        "Almost there…",
        "Polishing citations…",
    ],
    "DEFAULT": [
        "Still working…",
        "Hang tight…",
    ],
}


def _step_number(state: str) -> int:
    if state == "RESPOND":
        return TOTAL_STEPS
    try:
        return STEP_ORDER.index(state) + 1
    except ValueError:
        return 1


def _stepper_html(active_state: str) -> str:
    active_idx = _step_number(active_state) - 1
    parts: list[str] = []
    for i, label in enumerate(_STEP_LABELS):
        cls = "le-seg"
        if i < active_idx:
            cls += " done"
        elif i == active_idx:
            cls += " active"
        parts.append(f'<span class="{cls}">{label}</span>')
    return '<div class="le-stepper">' + "".join(parts) + "</div>"


def _micro_copy_for(state: str, elapsed_s: float) -> str:
    options = _MICRO_COPY.get(state) or _MICRO_COPY["DEFAULT"]
    if len(options) == 1:
        return options[0]
    idx = int(elapsed_s // MICRO_COPY_ROTATE_S) % len(options)
    return options[idx]


def render_state(ph: Any, state: str, label: str) -> None:
    icon = STATE_ICONS.get(state, "⏳")
    step = _step_number(state)
    html = (
        f"{_stepper_html(state)}"
        f"<p class='le-state'>{icon} {label}</p>"
        f"<p class='le-step-count'>{step}/{TOTAL_STEPS}</p>"
    )
    ph.markdown(html, unsafe_allow_html=True)


def render_progress_panel(
    ph: Any,
    state: str,
    label: str,
    *,
    elapsed_s: float,
    micro_copy: str = "",
) -> None:
    icon = STATE_ICONS.get(state, "⏳")
    elapsed_i = int(elapsed_s)
    html = (
        f"{_stepper_html(state)}"
        f"<p class='le-state'>{icon} {label}</p>"
        f"<p class='le-elapsed'>{elapsed_i}s elapsed</p>"
    )
    if micro_copy:
        html += f"<p class='le-micro'>{micro_copy}</p>"
    ph.markdown(html, unsafe_allow_html=True)


def render_skeleton(ph: Any) -> None:
    lines = "".join(
        f"<div class='le-line le-shimmer le-skeleton'></div>" for _ in range(4)
    )
    ph.markdown(f"<div class='le-skeleton-wrap'>{lines}</div>", unsafe_allow_html=True)


def _parse_sse_data_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "state": data.get("state"),
        "label": data.get("label"),
        "timestamp": data.get("timestamp"),
    }


def iter_sse_events(session_id: str, *, base_url: str = "http://127.0.0.1:8000") -> Iterator[dict[str, Any]]:
    url = f"{base_url}/chat/stream/{session_id}"
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            evt = _parse_sse_data_line(raw)
            if not evt or not evt.get("state"):
                continue
            yield evt
            if evt["state"] == "RESPOND":
                return


def run_chat_with_loading(
    progress_ph: Any,
    skeleton_ph: Any,
    *,
    session_id: str,
    repo_id: str,
    question: str,
    chat_callable: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    t0 = time.monotonic()
    result: dict[str, Any] = {}
    last_state = "INTAKE"
    last_label = "Preparing your request…"
    last_event_at = t0
    lock = threading.Lock()

    def _chat_worker() -> None:
        result.update(chat_callable(repo_id, question, session_id=session_id))

    chat_thread = threading.Thread(target=_chat_worker, daemon=True)
    chat_thread.start()

    def _render(state: str, label: str) -> None:
        elapsed = time.monotonic() - t0
        render_progress_panel(
            progress_ph,
            state,
            label,
            elapsed_s=elapsed,
            micro_copy=_micro_copy_for(state, elapsed),
        )

    sse_done = threading.Event()

    def _sse_worker() -> None:
        nonlocal last_state, last_label, last_event_at
        try:
            for evt in iter_sse_events(session_id):
                with lock:
                    last_state = str(evt.get("state") or last_state)
                    last_label = str(evt.get("label") or last_label)
                    last_event_at = time.monotonic()
                _render(last_state, last_label)
                if last_state == "FINALIZE":
                    render_skeleton(skeleton_ph)
                if last_state == "RESPOND":
                    break
        finally:
            sse_done.set()

    sse_thread = threading.Thread(target=_sse_worker, daemon=True)
    sse_thread.start()

    _render(last_state, last_label)

    while chat_thread.is_alive():
        now = time.monotonic()
        with lock:
            stalled = (now - last_event_at) >= STREAM_STALL_TIMEOUT_S
            state = last_state
            label = last_label
        if stalled:
            _render(state, label)
            with lock:
                last_event_at = now
        time.sleep(0.05)

    chat_thread.join(timeout=30)
    sse_thread.join(timeout=5)
    return result
