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
    theme = active_theme()
    st.markdown(
        f"""
<div class="hero-banner">
  <div class="hero-brand"><span class="mark">{theme.brand_logo}</span>{theme.brand_name}</div>
  <p class="hero-tagline">{theme.brand_tagline}. Ask architecture questions, explore call graphs, and verify answers with citations.</p>
  <div class="hero-cta-row">
    <span class="hero-chip">Hybrid RAG</span>
    <span class="hero-chip">Live agent steps</span>
    <span class="hero-chip">Voice in / out</span>
    <span class="hero-chip">RAGAS eval</span>
  </div>
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


def render_backend_status() -> bool:
    """Ping backend; show sidebar indicator. Returns True if online."""
    import api_client

    try:
        import requests

        r = requests.get(f"{api_client.API_BASE_URL}/health", timeout=3)
        online = r.status_code == 200
    except Exception:
        online = False

    if online:
        st.sidebar.markdown(
            f'<span class="pill pill-success">● API online</span>',
            unsafe_allow_html=True,
        )
        st.sidebar.caption(api_client.API_BASE_URL)
    else:
        st.sidebar.markdown(
            '<span class="pill pill-error">● API offline</span>',
            unsafe_allow_html=True,
        )
        st.sidebar.caption("Start uvicorn on :8000")
    return online


def section_header(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def render_empty_chat() -> None:
    open_tag = apply_branding("chat")
    st.markdown(
        f"""
{open_tag}
<div class="chat-empty">
  <p class="empty-title">Ask anything about this codebase</p>
  <p class="empty-hint">Every answer cites real files and lines. Start with a prompt below — or type your own.</p>
  <div class="prompt-row">
    <span class="prompt-chip">How does Session.send work?</span>
    <span class="prompt-chip">Where is HTTPBasicAuth defined?</span>
    <span class="prompt-chip">What calls the login flow?</span>
  </div>
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
