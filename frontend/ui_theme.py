"""
frontend/ui_theme.py
--------------------
Professional UI styling and reusable layout components for Streamlit.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

APP_VERSION = "1.0.0"


def inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

#MainMenu, footer, header { visibility: hidden; height: 0; }

.block-container {
    padding-top: 1.25rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

.hero-banner {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #6366f1 100%);
    border-radius: 16px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
    color: white;
    box-shadow: 0 10px 40px rgba(79, 70, 229, 0.25);
}

.hero-banner h1 {
    font-size: 1.75rem;
    font-weight: 700;
    margin: 0 0 0.35rem 0;
    color: white !important;
}

.hero-banner p {
    margin: 0;
    opacity: 0.92;
    font-size: 0.95rem;
}

.stat-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    height: 100%;
}

.stat-card .label {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748b;
    margin-bottom: 0.25rem;
}

.stat-card .value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #0f172a;
}

.pill {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}

.pill-success { background: #dcfce7; color: #166534; }
.pill-warning { background: #fef3c7; color: #92400e; }
.pill-error   { background: #fee2e2; color: #991b1b; }
.pill-info    { background: #e0e7ff; color: #3730a3; }

.section-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #0f172a;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

.ingest-panel {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}

.sidebar-brand {
    font-size: 1rem;
    font-weight: 700;
    color: #6366f1;
    margin-bottom: 0.5rem;
}

div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}

div[data-testid="stSidebar"] .stMarkdown,
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] .stCaption {
    color: #e2e8f0 !important;
}

div[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 8px;
    font-weight: 600;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: transparent;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 0.6rem 1.25rem;
    font-weight: 600;
}

.chat-empty {
    text-align: center;
    padding: 3rem 2rem;
    color: #64748b;
    border: 2px dashed #cbd5e1;
    border-radius: 14px;
    background: #f8fafc;
}

.footer-bar {
    text-align: center;
    color: #94a3b8;
    font-size: 0.8rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid #e2e8f0;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
<div class="hero-banner">
  <h1>CodeNavigator</h1>
  <p>Ingest any GitHub repo · Ask architecture questions · Run RAGAS eval · Golden-set CI</p>
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
        st.sidebar.markdown("🟢 **Backend online**", help=api_client.API_BASE_URL)
    else:
        st.sidebar.error("Backend offline — start uvicorn on :8000")
    return online


def section_header(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def render_empty_chat() -> None:
    st.markdown(
        """
<div class="chat-empty">
  <p style="font-size:1.1rem;margin-bottom:0.5rem;">💬 Ask anything about the codebase</p>
  <p style="font-size:0.9rem;margin:0;">Try: <em>How does Session.send work?</em> or <em>Where is HTTPBasicAuth defined?</em></p>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_ragas_chart(scores: dict[str, Any]) -> None:
    import pandas as pd

    if not scores:
        return
    df = pd.DataFrame(list(scores.items()), columns=["Metric", "Score"])
    st.bar_chart(df.set_index("Metric"), color="#6366f1", height=280)


def render_footer() -> None:
    st.markdown(
        f'<div class="footer-bar">CodeNavigator v{APP_VERSION} · Hybrid RAG · Groq/Ollama</div>',
        unsafe_allow_html=True,
    )
