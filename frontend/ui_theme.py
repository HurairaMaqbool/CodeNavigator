# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/ui_theme.py
--------------------
Layout helpers for Streamlit. Visual tokens come from ``frontend/theme.py``
(Module #34) — this module must not hardcode palette/font/spacing values.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from theme import active_theme, apply_branding, boot_theme
except ImportError:
    from frontend.theme import active_theme, apply_branding, boot_theme

APP_VERSION = "1.0.0"


def inject_styles() -> None:
    """Boot the shared design system once (dark default) and inject CSS."""
    boot_theme()


def render_hero() -> None:
    """Compact hero — main brand lives in top bar; this shows feature chips only."""
    theme = active_theme()
    st.markdown(
        f"""
<div class="hero-banner" style="padding:1.5rem 1.75rem;margin-bottom:1.25rem">
  <div class="hero-cta-row">
    <span class="hero-chip">Hybrid RAG</span>
    <span class="hero-chip">Live agent steps</span>
    <span class="hero-chip">Verified citations</span>
    <span class="hero-chip">RAGAS eval</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_top_header(online: bool) -> None:
    """Branded header with API status pill — persistent top-right visibility."""
    theme = active_theme()
    import api_client

    pill_class = "online" if online else "offline"
    label = "API online" if online else "API offline"
    st.markdown(
        f"""
<div class="cn-topbar">
  <div>
    <div class="cn-topbar-brand">
      <span class="mark">{theme.brand_logo}</span>
      <span>{theme.brand_name}</span>
    </div>
    <p class="cn-topbar-tagline">{theme.brand_tagline}</p>
  </div>
  <div class="cn-api-pill {pill_class}">
    <span class="dot"></span>
    <span>{label}</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    if online:
        st.caption(api_client.API_BASE_URL)


def render_sidebar_nav(current: str) -> str:
    """Vertical nav with icon + label; returns selected page id."""
    labels = {
        "Workspace": "◈  Workspace",
        "Evaluation & QA": "◇  Evaluation",
        "Platform": "▣  Platform",
    }
    pages = list(labels.keys())
    choice = st.sidebar.radio(
        "Navigate",
        pages,
        index=pages.index(current) if current in pages else 0,
        format_func=lambda p: labels[p],
        key="cn_nav_radio",
    )
    return choice


def render_ingest_stepper(sync_status: str) -> None:
    """Multi-step ingest progress: Clone → Filter → Parse → Chunk → Index → Synced."""
    steps = [
        ("clone", "Clone"),
        ("filter", "Filter"),
        ("parse", "Parse"),
        ("chunk", "Chunk"),
        ("index", "Index"),
        ("synced", "Synced"),
    ]
    order = [s[0] for s in steps]
    active_idx = 0
    if sync_status == "synced":
        active_idx = len(steps)
    elif sync_status in ("indexing", "parsing", "filtering", "cloning"):
        mapping = {
            "cloning": 0,
            "filtering": 1,
            "parsing": 2,
            "indexing": 4,
        }
        active_idx = mapping.get(sync_status, 3) + 1

    html_parts = ['<div class="cn-stepper">']
    for i, (_, label) in enumerate(steps):
        if i < active_idx:
            cls = "done"
        elif i == active_idx and sync_status != "synced":
            cls = "active"
        elif sync_status == "synced":
            cls = "done"
        else:
            cls = ""
        html_parts.append(f'<div class="cn-step {cls}">{label}</div>')
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_alert(kind: str, message: str, *, icon: str = "") -> None:
    """Semantic alert — error / warning / info (never reuse yellow for both)."""
    icons = {"error": "⚠️", "warning": "⏳", "info": "ℹ️"}
    ic = icon or icons.get(kind, "•")
    css = f"cn-alert cn-alert-{kind}" if kind in ("error", "warning", "info") else "cn-alert cn-alert-info"
    st.markdown(
        f'<div class="{css}"><span>{ic}</span><span>{message}</span></div>',
        unsafe_allow_html=True,
    )


def render_citation_chips(sources: list[dict]) -> None:
    """Inline citation chips for source panel — monospace file:line."""
    if not sources:
        return
    chips = []
    for s in sources:
        path = s.get("file_path", "")
        fn = s.get("function_name") or ""
        lines = s.get("lines") or s.get("start_line")
        if lines and isinstance(lines, int):
            line_s = str(lines)
        elif lines:
            line_s = str(lines)
        else:
            line_s = "—"
        label = f"{path}:{line_s}" if path else fn
        if fn and path:
            label = f"{path} · {fn}"
        chips.append(f'<span class="cn-cite-chip">{label}</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)


def render_empty_stats() -> None:
    st.markdown(
        """
<div class="cn-empty-stat">
  <div class="icon">📂</div>
  <div>No files indexed yet</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_stat_card(label: str, value: str, col) -> None:
    with col:
        st.markdown(
            f"""
<div class="stat-card">
  <div class="label">{label}</div>
  <div class="value">{value}</div>
</div>
            """,
            unsafe_allow_html=True,
        )


def status_pill_html(status: str) -> str:
    mapping = {
        "synced": ("Ready", "pill-success"),
        "pending": ("Indexing", "pill-warning"),
        "failed": ("Failed", "pill-error"),
        "pass": ("Pass", "pill-success"),
        "fail": ("Fail", "pill-error"),
    }
    text, css = mapping.get(status, (status.title(), "pill-info"))
    return f'<span class="pill {css}">{text}</span>'


def check_backend_online() -> bool:
    """Ping backend health endpoint. Returns True if online."""
    import api_client

    try:
        import requests

        r = requests.get(f"{api_client.API_BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def render_backend_status() -> bool:
    """Backward-compatible alias — status pill lives in ``render_top_header``."""
    return check_backend_online()


def section_header(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def render_empty_chat() -> None:
    st.markdown(
        """
<div class="chat-empty">
  <p class="empty-title" style="font-size:1.25rem">Ask anything about this codebase</p>
  <p class="empty-hint">Every answer cites real files and line numbers. Pick a starter prompt or type your own below.</p>
  <div class="prompt-row">
    <span class="prompt-chip">How does Session.send work?</span>
    <span class="prompt-chip">Where is HTTPBasicAuth defined?</span>
    <span class="prompt-chip">The role of urllib3.PoolManager</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_workspace() -> None:
    """Shown before a repository is ingested — one clear next step."""
    st.markdown(
        """
<div class="chat-empty" style="margin-top:0.5rem">
  <p class="empty-title">Ingest a repository to begin</p>
  <p class="empty-hint">Paste a public GitHub URL above, or pick a Quick start repo in the sidebar. Chat, diagrams, and eval unlock once indexing finishes.</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_ragas_chart(scores: dict[str, Any]) -> None:
    import pandas as pd

    try:
        from theme import active_theme
    except ImportError:
        from frontend.theme import active_theme

    if not scores:
        return
    df = pd.DataFrame(list(scores.items()), columns=["Metric", "Score"])
    accent = active_theme().colors.teal_400
    st.bar_chart(df.set_index("Metric"), color=accent, height=280)


def render_footer() -> None:
    theme = active_theme()
    st.markdown(
        f'<div class="footer-bar">{theme.brand_name} v{APP_VERSION} · Hybrid RAG · Citations · Eval</div>',
        unsafe_allow_html=True,
    )
