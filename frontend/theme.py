# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/theme.py
-----------------
Module #34 — Shared design system (navy / blue / teal, dark-mode-first).

Streamlit-only (same framework as Modules #31–#33). Every frontend surface
pulls tokens from ``get_theme()``; ``apply_branding()`` injects CSS variables
and branded wrappers for chat, sidebar, and diagrams.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Literal

import streamlit as st

ThemeMode = Literal["dark", "light"]

# Per-session mode preference (Streamlit session_state only).
THEME_MODE_SESSION_KEY = "theme_mode"
DEFAULT_THEME_MODE: ThemeMode = "dark"

BRAND_NAME = "CodeNavigator"
BRAND_LOGO = "⚡"
BRAND_TAGLINE = "Understand any codebase in minutes"

# Loaded once at startup; reused by every surface (not recomputed per render).
_ACTIVE_THEME: "ThemeTokens | None" = None


@dataclass(frozen=True)
class ColorTokens:
    # Navy / blue / teal brand palette
    navy_900: str
    navy_800: str
    navy_700: str
    blue_600: str
    blue_500: str
    blue_400: str
    teal_500: str
    teal_400: str
    # Surfaces & text
    bg: str
    surface: str
    surface_elevated: str
    border: str
    text: str
    text_muted: str
    text_inverse: str
    # Semantic
    success_bg: str
    success_fg: str
    warning_bg: str
    warning_fg: str
    danger_bg: str
    danger_fg: str
    info_bg: str
    info_fg: str
    # Accents used by voice / loading widgets
    accent: str
    accent_strong: str
    skeleton_a: str
    skeleton_b: str
    hero_gradient: str
    sidebar_gradient: str


@dataclass(frozen=True)
class TypographyTokens:
    font_family: str
    font_mono: str
    font_import_url: str
    size_xs: str
    size_sm: str
    size_base: str
    size_lg: str
    size_xl: str
    size_2xl: str
    size_3xl: str
    size_display: str
    weight_regular: int
    weight_medium: int
    weight_semibold: int
    weight_bold: int


@dataclass(frozen=True)
class SpacingTokens:
    """4px base unit progression: 4 → 8 → 12 → 16 → 24 → 32 → 48 → 64."""

    unit: int
    xs: str
    sm: str
    md: str
    lg: str
    xl: str
    xxl: str
    xxxl: str
    huge: str
    radius_sm: str
    radius_md: str
    radius_lg: str
    radius_pill: str
    max_content_width: str


@dataclass(frozen=True)
class ThemeTokens:
    mode: ThemeMode
    brand_name: str
    brand_logo: str
    brand_tagline: str
    colors: ColorTokens
    typography: TypographyTokens
    spacing: SpacingTokens

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TYPOGRAPHY = TypographyTokens(
    font_family="'Inter', 'Manrope', system-ui, sans-serif",
    font_mono="'JetBrains Mono', 'Fira Code', Consolas, monospace",
    font_import_url=(
        "https://fonts.googleapis.com/css2?"
        "family=Inter:wght@400;500;600;700&"
        "family=Manrope:wght@500;600;700&"
        "family=JetBrains+Mono:wght@400;500&display=swap"
    ),
    size_xs="0.75rem",      # 12px meta/labels
    size_sm="0.875rem",     # 14px secondary
    size_base="1rem",       # 16px body
    size_lg="1.125rem",
    size_xl="1.25rem",      # 20px section headers
    size_2xl="1.75rem",     # 28px page title
    size_3xl="1.875rem",
    size_display="1.75rem",
    weight_regular=400,
    weight_medium=500,
    weight_semibold=600,
    weight_bold=700,
)

_SPACING = SpacingTokens(
    unit=8,
    xs="8px",
    sm="8px",
    md="16px",
    lg="16px",
    xl="24px",
    xxl="32px",
    xxxl="48px",
    huge="64px",
    radius_sm="8px",
    radius_md="12px",
    radius_lg="16px",
    radius_pill="999px",
    max_content_width="1200px",
)

# Indigo-violet primary · coral accent · cool slate neutrals
_DARK_COLORS = ColorTokens(
    navy_900="#0F172A",
    navy_800="#1E293B",
    navy_700="#334155",
    blue_600="#4F46E5",
    blue_500="#6366F1",
    blue_400="#818CF8",
    teal_500="#F97316",
    teal_400="#FB923C",
    bg="#0F172A",
    surface="#1E293B",
    surface_elevated="#243044",
    border="#334155",
    text="#F1F5F9",
    text_muted="#94A3B8",
    text_inverse="#0F172A",
    success_bg="#064E3B",
    success_fg="#10B981",
    warning_bg="#78350F",
    warning_fg="#F59E0B",
    danger_bg="#7F1D1D",
    danger_fg="#EF4444",
    info_bg="#1E3A5F",
    info_fg="#3B82F6",
    accent="#F97316",
    accent_strong="#6366F1",
    skeleton_a="#1E293B",
    skeleton_b="#334155",
    hero_gradient=(
        "radial-gradient(900px 400px at 10% -10%, rgba(99,102,241,0.35), transparent 55%),"
        "radial-gradient(700px 360px at 90% 0%, rgba(249,115,22,0.18), transparent 50%),"
        "linear-gradient(145deg, #0F172A 0%, #1E293B 100%)"
    ),
    sidebar_gradient="linear-gradient(180deg, #0F172A 0%, #1E293B 100%)",
)

_LIGHT_COLORS = ColorTokens(
    navy_900="#0F172A",
    navy_800="#1E293B",
    navy_700="#334155",
    blue_600="#4F46E5",
    blue_500="#6366F1",
    blue_400="#818CF8",
    teal_500="#F97316",
    teal_400="#F97316",
    bg="#F8FAFC",
    surface="#FFFFFF",
    surface_elevated="#FFFFFF",
    border="#E2E8F0",
    text="#0F172A",
    text_muted="#475569",
    text_inverse="#FFFFFF",
    success_bg="#D1FAE5",
    success_fg="#059669",
    warning_bg="#FEF3C7",
    warning_fg="#D97706",
    danger_bg="#FEE2E2",
    danger_fg="#DC2626",
    info_bg="#DBEAFE",
    info_fg="#2563EB",
    accent="#F97316",
    accent_strong="#6366F1",
    skeleton_a="#E2E8F0",
    skeleton_b="#F1F5F9",
    hero_gradient=(
        "radial-gradient(900px 400px at 8% -20%, rgba(99,102,241,0.14), transparent 55%),"
        "radial-gradient(700px 360px at 92% 0%, rgba(249,115,22,0.10), transparent 50%),"
        "linear-gradient(145deg, #4F46E5 0%, #6366F1 48%, #818CF8 100%)"
    ),
    sidebar_gradient="linear-gradient(180deg, #0F172A 0%, #1E293B 100%)",
)


@lru_cache(maxsize=2)
def get_theme(mode: ThemeMode | str | None = "dark") -> ThemeTokens:
    """
    Return the shared token object for ``dark`` (default) or ``light``.

    Cached once per mode — callers must not rebuild palettes ad hoc.
    Missing / invalid mode → dark (never an unstyled fallback).
    """
    resolved: ThemeMode = "dark"
    if isinstance(mode, str) and mode.strip().lower() == "light":
        resolved = "light"
    colors = _LIGHT_COLORS if resolved == "light" else _DARK_COLORS
    return ThemeTokens(
        mode=resolved,
        brand_name=BRAND_NAME,
        brand_logo=BRAND_LOGO,
        brand_tagline=BRAND_TAGLINE,
        colors=colors,
        typography=_TYPOGRAPHY,
        spacing=_SPACING,
    )


def resolve_session_mode() -> ThemeMode:
    """Read session preference; absent/invalid → dark."""
    raw = None
    try:
        raw = st.session_state.get(THEME_MODE_SESSION_KEY)
    except Exception:
        raw = None
    if raw is None or str(raw).strip() == "":
        return DEFAULT_THEME_MODE
    if str(raw).strip().lower() == "light":
        return "light"
    return "dark"


def set_theme_mode(mode: ThemeMode | str) -> None:
    """Persist dark/light for the current Streamlit session only."""
    resolved: ThemeMode = "light" if str(mode).strip().lower() == "light" else "dark"
    st.session_state[THEME_MODE_SESSION_KEY] = resolved
    global _ACTIVE_THEME
    _ACTIVE_THEME = get_theme(resolved)


def active_theme() -> ThemeTokens:
    """Startup-loaded theme (or dark if boot has not run yet)."""
    global _ACTIVE_THEME
    if _ACTIVE_THEME is None:
        _ACTIVE_THEME = get_theme(DEFAULT_THEME_MODE)
    return _ACTIVE_THEME


def css_variables(theme: ThemeTokens | None = None) -> str:
    """CSS custom properties derived from the token object."""
    t = theme or active_theme()
    c, ty, sp = t.colors, t.typography, t.spacing
    return f"""
:root {{
  --cn-navy-900: {c.navy_900};
  --cn-navy-800: {c.navy_800};
  --cn-navy-700: {c.navy_700};
  --cn-blue-600: {c.blue_600};
  --cn-blue-500: {c.blue_500};
  --cn-blue-400: {c.blue_400};
  --cn-teal-500: {c.teal_500};
  --cn-teal-400: {c.teal_400};
  --cn-bg: {c.bg};
  --cn-surface: {c.surface};
  --cn-surface-elevated: {c.surface_elevated};
  --cn-border: {c.border};
  --cn-text: {c.text};
  --cn-text-muted: {c.text_muted};
  --cn-text-inverse: {c.text_inverse};
  --cn-accent: {c.accent};
  --cn-accent-strong: {c.accent_strong};
  --cn-primary-tint: {"#EEF2FF" if t.mode == "light" else "rgba(99, 102, 241, 0.16)"};
  --cn-primary-tint-hover: {"#E0E7FF" if t.mode == "light" else "rgba(99, 102, 241, 0.28)"};
  --cn-skeleton-a: {c.skeleton_a};
  --cn-skeleton-b: {c.skeleton_b};
  --cn-success-bg: {c.success_bg};
  --cn-success-fg: {c.success_fg};
  --cn-warning-bg: {c.warning_bg};
  --cn-warning-fg: {c.warning_fg};
  --cn-danger-bg: {c.danger_bg};
  --cn-danger-fg: {c.danger_fg};
  --cn-info-bg: {c.info_bg};
  --cn-info-fg: {c.info_fg};
  --cn-hero-gradient: {c.hero_gradient};
  --cn-sidebar-gradient: {c.sidebar_gradient};
  --cn-font: {ty.font_family};
  --cn-font-mono: {ty.font_mono};
  --cn-size-xs: {ty.size_xs};
  --cn-size-sm: {ty.size_sm};
  --cn-size-base: {ty.size_base};
  --cn-size-lg: {ty.size_lg};
  --cn-size-xl: {ty.size_xl};
  --cn-size-2xl: {ty.size_2xl};
  --cn-size-3xl: {ty.size_3xl};
  --cn-size-display: {ty.size_display};
  --cn-space-xs: {sp.xs};
  --cn-space-sm: {sp.sm};
  --cn-space-md: {sp.md};
  --cn-space-lg: {sp.lg};
  --cn-space-xl: {sp.xl};
  --cn-space-xxl: {sp.xxl};
  --cn-radius-sm: {sp.radius_sm};
  --cn-radius-md: {sp.radius_md};
  --cn-radius-lg: {sp.radius_lg};
  --cn-radius-pill: {sp.radius_pill};
  --cn-max-width: {sp.max_content_width};
}}
"""


def _global_stylesheet(theme: ThemeTokens) -> str:
    ty = theme.typography
    return f"""
@import url('{ty.font_import_url}');
{css_variables(theme)}

html, body, [class*="css"], .stApp {{
    font-family: var(--cn-font);
    background:
      radial-gradient(900px 420px at 100% 0%, rgba(45,212,191,0.06), transparent 45%),
      radial-gradient(700px 380px at 0% 100%, rgba(37,99,235,0.07), transparent 40%),
      var(--cn-bg);
    color: var(--cn-text);
    letter-spacing: 0.01em;
}}

#MainMenu, footer, header {{ visibility: hidden; height: 0; }}

.block-container {{
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: var(--cn-max-width);
    animation: cn-page-fade-in 0.28s ease-out both;
}}

@keyframes cn-page-fade-in {{
  from {{ opacity: 0; }}
  to {{ opacity: 1; }}
}}

.cn-page-content {{
    animation: cn-page-fade-in 0.28s ease-out both;
}}

/* Sidebar nav — stable during content fade */
section[data-testid="stSidebar"] div[role="radiogroup"] label {{
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, padding 0.15s ease;
    border-radius: var(--cn-radius-sm);
    border-left: 3px solid transparent;
    padding-left: 0.5rem !important;
}}

section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
    background: rgba(99, 102, 241, 0.18) !important;
    border-left-color: var(--cn-blue-500) !important;
    font-weight: 600;
}}

/* Screen skeleton (Evaluation / Platform layout shape) */
.cn-page-skeleton {{
    margin-bottom: var(--cn-space-lg);
}}
.cn-page-skeleton .cn-sk-title {{
    height: 18px;
    width: 42%;
    border-radius: 6px;
    margin-bottom: 0.75rem;
    background: linear-gradient(90deg, var(--cn-skeleton-a) 0px, var(--cn-skeleton-b) 40px, var(--cn-skeleton-a) 80px);
    background-size: 200px 100%;
    animation: cn-shimmer 1.6s ease-in-out infinite;
}}
.cn-page-skeleton .cn-sk-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 0.75rem;
}}
.cn-page-skeleton .cn-sk-card {{
    height: 72px;
    border-radius: var(--cn-radius-md);
    background: linear-gradient(90deg, var(--cn-skeleton-a) 0px, var(--cn-skeleton-b) 40px, var(--cn-skeleton-a) 80px);
    background-size: 200px 100%;
    animation: cn-shimmer 1.6s ease-in-out infinite;
}}
.cn-page-skeleton .cn-sk-block {{
    height: 120px;
    border-radius: var(--cn-radius-md);
    background: linear-gradient(90deg, var(--cn-skeleton-a) 0px, var(--cn-skeleton-b) 40px, var(--cn-skeleton-a) 80px);
    background-size: 200px 100%;
    animation: cn-shimmer 1.6s ease-in-out infinite;
}}
@keyframes cn-shimmer {{
  0% {{ background-position: -200px 0; }}
  100% {{ background-position: calc(200px + 100%) 0; }}
}}

/* —— Hero (brand-first, full-bleed atmosphere) —— */
.hero-banner {{
    position: relative;
    overflow: hidden;
    background: var(--cn-hero-gradient);
    border-radius: var(--cn-radius-lg);
    padding: 2.75rem 2.5rem 2.5rem;
    margin-bottom: var(--cn-space-xl);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow:
      0 24px 60px rgba(7, 21, 37, 0.45),
      inset 0 1px 0 rgba(255,255,255,0.08);
    animation: cn-hero-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}}

.hero-banner::before {{
    content: "";
    position: absolute;
    inset: 0;
    background:
      linear-gradient(120deg, transparent 40%, rgba(255,255,255,0.04) 50%, transparent 60%);
    background-size: 200% 100%;
    animation: cn-sheen 8s ease-in-out infinite;
    pointer-events: none;
}}

.hero-banner .hero-brand {{
    font-family: 'Sora', var(--cn-font);
    font-size: clamp(2rem, 4vw, 2.75rem);
    font-weight: 700;
    letter-spacing: -0.03em;
    margin: 0 0 0.5rem 0;
    color: #FFFFFF !important;
    line-height: 1.1;
    position: relative;
}}

.hero-banner .hero-brand span.mark {{
    color: var(--cn-teal-400);
    margin-right: 0.35rem;
    filter: drop-shadow(0 0 8px rgba(249,115,22,0.35));
}}

.hero-banner .hero-tagline {{
    margin: 0 0 1.25rem 0;
    max-width: 34rem;
    font-size: 1.05rem;
    line-height: 1.55;
    color: rgba(241,245,249,0.88);
    position: relative;
}}

.hero-banner .hero-cta-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    position: relative;
}}

.hero-chip {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.4rem 0.85rem;
    border-radius: var(--cn-radius-pill);
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.14);
    color: #FFFFFF;
    backdrop-filter: blur(8px);
}}

@keyframes cn-hero-in {{
  from {{ opacity: 0; transform: translateY(12px); }}
  to {{ opacity: 1; transform: none; }}
}}
@keyframes cn-sheen {{
  0%, 100% {{ background-position: 120% 0; }}
  50% {{ background-position: -20% 0; }}
}}
@keyframes cn-fade-up {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to {{ opacity: 1; transform: none; }}
}}

/* —— Cards & panels —— */
.stat-card {{
    background: var(--cn-surface);
    border: 1px solid var(--cn-border);
    border-radius: var(--cn-radius-md);
    padding: 1.15rem 1.35rem;
    box-shadow: 0 8px 24px rgba(7, 21, 37, 0.18);
    height: 100%;
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    animation: cn-fade-up 0.5s ease both;
}}

.stat-card:hover {{
    transform: translateY(-2px);
    border-color: rgba(45, 212, 191, 0.35);
    box-shadow: 0 14px 32px rgba(7, 21, 37, 0.28);
}}

.stat-card .label {{
    font-size: 0.7rem;
    font-weight: {ty.weight_semibold};
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--cn-text-muted);
    margin-bottom: 0.4rem;
}}

.stat-card .value {{
    font-family: 'Sora', var(--cn-font);
    font-size: 1.55rem;
    font-weight: {ty.weight_bold};
    color: var(--cn-text);
    letter-spacing: -0.02em;
}}

.pill {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.8rem;
    border-radius: var(--cn-radius-pill);
    font-size: 0.72rem;
    font-weight: {ty.weight_semibold};
    letter-spacing: 0.03em;
    border: 1px solid transparent;
}}

.pill-success {{ background: var(--cn-success-bg); color: var(--cn-success-fg); border-color: rgba(94,234,212,0.25); }}
.pill-warning {{ background: var(--cn-warning-bg); color: var(--cn-warning-fg); border-color: rgba(251,191,36,0.25); }}
.pill-error   {{ background: var(--cn-danger-bg); color: var(--cn-danger-fg); border-color: rgba(252,165,165,0.25); }}
.pill-info    {{ background: var(--cn-info-bg); color: var(--cn-info-fg); border-color: rgba(147,197,253,0.25); }}

.section-header {{
    font-family: 'Sora', var(--cn-font);
    font-size: 1.15rem;
    font-weight: {ty.weight_semibold};
    color: var(--cn-text);
    margin: 1.75rem 0 0.85rem 0;
    padding-bottom: 0.65rem;
    border-bottom: 1px solid var(--cn-border);
    letter-spacing: -0.02em;
    position: relative;
}}

.section-header::after {{
    content: "";
    position: absolute;
    left: 0;
    bottom: -1px;
    width: 3.25rem;
    height: 2px;
    background: linear-gradient(90deg, var(--cn-teal-400), var(--cn-blue-500));
    border-radius: 2px;
}}

.ingest-panel {{
    background: var(--cn-surface);
    border: 1px solid var(--cn-border);
    border-radius: var(--cn-radius-lg);
    padding: 1.5rem 1.65rem 1.35rem;
    margin-bottom: 1.35rem;
    box-shadow: 0 10px 28px rgba(7, 21, 37, 0.2);
    animation: cn-fade-up 0.55s ease 0.05s both;
}}

.sidebar-brand {{
    font-family: 'Sora', var(--cn-font);
    font-size: 1.05rem;
    font-weight: {ty.weight_bold};
    color: var(--cn-teal-400);
    margin-bottom: 0.35rem;
    letter-spacing: -0.02em;
}}

.sidebar-brand-sub {{
    font-size: 0.75rem;
    color: rgba(226,232,240,0.65);
    margin-bottom: 0.75rem;
}}

div[data-testid="stSidebar"] {{
    background: var(--cn-sidebar-gradient);
    border-right: 1px solid rgba(36, 59, 85, 0.85);
}}

div[data-testid="stSidebar"] .stMarkdown,
div[data-testid="stSidebar"] label,
div[data-testid="stSidebar"] .stCaption {{
    color: var(--cn-text) !important;
}}

div[data-testid="stSidebar"] .stCaption {{
    opacity: 0.72;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
}}

div[data-testid="stSidebar"] .stButton > button {{
    width: 100%;
    border-radius: var(--cn-radius-sm);
    font-weight: {ty.weight_semibold};
    border: 1px solid rgba(45, 212, 191, 0.22);
    background: rgba(255,255,255,0.04);
    color: var(--cn-text);
    transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}}

div[data-testid="stSidebar"] .stButton > button:hover {{
    background: rgba(45, 212, 191, 0.12);
    border-color: rgba(45, 212, 191, 0.45);
    transform: translateY(-1px);
}}

div[data-testid="stSidebar"] .stRadio > label {{
    font-weight: 600;
}}

/* Primary actions — indigo solid */
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {{
    background: var(--cn-blue-500) !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    border-radius: var(--cn-radius-md) !important;
    box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
    transition: background 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}}

.stButton > button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {{
    background: var(--cn-blue-600) !important;
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4);
}}

/* Secondary / ghost buttons */
.stButton > button[kind="secondary"],
button[data-testid="baseButton-secondary"] {{
    background: transparent !important;
    border: 1px solid var(--cn-border) !important;
    color: var(--cn-text) !important;
    border-radius: var(--cn-radius-md) !important;
    font-weight: 500 !important;
}}

.stTextInput > div > div > input,
.stTextArea textarea {{
    border-radius: var(--cn-radius-sm) !important;
    border-color: var(--cn-border) !important;
    background: var(--cn-surface-elevated) !important;
}}

.chat-empty {{
    text-align: left;
    padding: 2rem 1.75rem;
    color: var(--cn-text-muted);
    border: 1px solid var(--cn-border);
    border-radius: var(--cn-radius-lg);
    background:
      linear-gradient(160deg, rgba(45,212,191,0.06), transparent 40%),
      var(--cn-surface);
    box-shadow: 0 8px 24px rgba(7, 21, 37, 0.16);
    animation: cn-fade-up 0.55s ease 0.1s both;
}}

.chat-empty .empty-title {{
    font-family: 'Sora', var(--cn-font);
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--cn-text);
    margin: 0 0 0.45rem 0;
    letter-spacing: -0.02em;
}}

.chat-empty .empty-hint {{
    margin: 0 0 1rem 0;
    font-size: 0.92rem;
    line-height: 1.5;
}}

.chat-empty .prompt-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}}

.chat-empty .prompt-chip {{
    font-size: 0.8125rem;
    padding: 0.5rem 1rem;
    border-radius: var(--cn-radius-pill);
    background: var(--cn-primary-tint);
    border: 1px solid rgba(99, 102, 241, 0.25);
    color: var(--cn-blue-500);
    font-weight: 500;
    transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
    cursor: default;
}}

.chat-empty .prompt-chip:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(99, 102, 241, 0.18);
    background: var(--cn-primary-tint-hover);
}}

.footer-bar {{
    text-align: center;
    color: var(--cn-text-muted);
    font-size: 0.78rem;
    margin-top: 2.5rem;
    padding-top: 1.1rem;
    border-top: 1px solid var(--cn-border);
    letter-spacing: 0.02em;
}}

.cn-brand-chat,
.cn-brand-sidebar,
.cn-brand-diagram {{
    font-family: var(--cn-font);
    color: var(--cn-text);
}}

.cn-brand-chat {{
    border-left: 3px solid var(--cn-teal-400);
    padding-left: var(--cn-space-md);
}}

.cn-brand-diagram {{
    border: 1px solid var(--cn-border);
    border-radius: var(--cn-radius-md);
    background: var(--cn-surface);
    padding: var(--cn-space-md);
    box-shadow: 0 8px 22px rgba(7, 21, 37, 0.16);
}}

/* Chat bubbles */
[data-testid="stChatMessage"] {{
    background: var(--cn-surface) !important;
    border: 1px solid var(--cn-border) !important;
    border-radius: var(--cn-radius-md) !important;
    padding: 0.85rem 1rem !important;
    margin-bottom: 0.65rem !important;
}}

div[data-testid="stStatusWidget"],
.stAlert {{
    border-radius: var(--cn-radius-md) !important;
}}

/* Soften Streamlit chrome */
[data-testid="stDecoration"] {{ display: none; }}

/* —— Top header bar (brand + API status) —— */
.cn-topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--cn-space-md) 0 var(--cn-space-lg);
    margin-bottom: var(--cn-space-sm);
    border-bottom: 1px solid var(--cn-border);
}}

.cn-topbar-brand {{
    display: flex;
    align-items: center;
    gap: 0.65rem;
    font-size: var(--cn-size-2xl);
    font-weight: 700;
    color: var(--cn-text);
    letter-spacing: -0.03em;
}}

.cn-topbar-brand .mark {{
    color: var(--cn-teal-400);
    font-size: 1.35em;
}}

.cn-topbar-tagline {{
    font-size: var(--cn-size-sm);
    color: var(--cn-text-muted);
    margin: 0.15rem 0 0 0;
    font-weight: 400;
}}

.cn-api-pill {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.4rem 0.9rem;
    border-radius: var(--cn-radius-pill);
    font-size: var(--cn-size-xs);
    font-weight: 600;
    border: 1px solid var(--cn-border);
    background: var(--cn-surface);
}}

.cn-api-pill .dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    animation: cn-pulse-dot 2s ease-in-out infinite;
}}

.cn-api-pill.online .dot {{ background: var(--cn-success-fg); box-shadow: 0 0 0 3px rgba(16,185,129,0.25); }}
.cn-api-pill.offline .dot {{ background: var(--cn-danger-fg); animation: none; }}

@keyframes cn-pulse-dot {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.5; }}
}}

/* —— Sidebar vertical nav (Streamlit radio styled as nav) —— */
div[data-testid="stSidebar"] .stRadio > div {{
    flex-direction: column !important;
    gap: 0.35rem;
}}

div[data-testid="stSidebar"] .stRadio label {{
    display: flex !important;
    align-items: center;
    gap: 0.65rem;
    padding: 0.65rem 0.85rem !important;
    border-radius: var(--cn-radius-md) !important;
    font-size: var(--cn-size-sm) !important;
    font-weight: 500 !important;
    color: rgba(241,245,249,0.9) !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    transition: background 0.18s ease, border-color 0.18s ease;
    cursor: pointer;
}}

div[data-testid="stSidebar"] .stRadio label:hover {{
    background: rgba(99, 102, 241, 0.12) !important;
    border-color: rgba(99, 102, 241, 0.2) !important;
}}

div[data-testid="stSidebar"] .stRadio label:has(input:checked) {{
    background: rgba(99, 102, 241, 0.22) !important;
    border-left: 3px solid var(--cn-blue-500) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
}}

div[data-testid="stSidebar"] .stRadio label > div:first-child {{
    display: none !important;
}}

.cn-nav {{
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin: 0.5rem 0 1rem;
}}

.cn-nav-item {{
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0.65rem 0.85rem;
    border-radius: var(--cn-radius-md);
    font-size: var(--cn-size-sm);
    font-weight: 500;
    color: rgba(241,245,249,0.85);
    border: 1px solid transparent;
    transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
    cursor: pointer;
    text-decoration: none;
}}

.cn-nav-item:hover {{
    background: rgba(99, 102, 241, 0.12);
    border-color: rgba(99, 102, 241, 0.2);
}}

.cn-nav-item.active {{
    background: rgba(99, 102, 241, 0.22);
    border-left: 3px solid var(--cn-blue-500);
    color: #FFFFFF;
    font-weight: 600;
}}

.cn-nav-icon {{
    width: 1.25rem;
    text-align: center;
    opacity: 0.9;
}}

/* —— Ingest progress stepper —— */
.cn-stepper {{
    display: flex;
    gap: 0.25rem;
    margin: var(--cn-space-md) 0;
    flex-wrap: wrap;
}}

.cn-step {{
    flex: 1;
    min-width: 4.5rem;
    text-align: center;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--cn-text-muted);
    position: relative;
    padding-bottom: 0.5rem;
}}

.cn-step::after {{
    content: "";
    display: block;
    height: 4px;
    border-radius: 2px;
    background: var(--cn-border);
    margin-top: 0.35rem;
    transition: background 0.2s ease;
}}

.cn-step.done {{ color: var(--cn-success-fg); }}
.cn-step.done::after {{ background: var(--cn-success-fg); }}
.cn-step.active {{ color: var(--cn-blue-500); }}
.cn-step.active::after {{ background: var(--cn-blue-500); }}

/* —— Panel cards —— */
.cn-panel-card {{
    background: var(--cn-surface);
    border: 1px solid var(--cn-border);
    border-radius: var(--cn-radius-lg);
    padding: var(--cn-space-lg);
    margin-bottom: var(--cn-space-md);
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}}

/* —— Citation chips —— */
.cn-cite-chip {{
    display: inline-flex;
    align-items: center;
    font-family: var(--cn-font-mono);
    font-size: 0.75rem;
    padding: 0.2rem 0.55rem;
    margin: 0.15rem 0.25rem 0.15rem 0;
    border-radius: var(--cn-radius-sm);
    background: var(--cn-primary-tint);
    color: var(--cn-blue-500);
    border: 1px solid rgba(99, 102, 241, 0.2);
}}

/* —— Semantic alert cards —— */
.cn-alert {{
    display: flex;
    gap: 0.65rem;
    align-items: flex-start;
    padding: var(--cn-space-md);
    border-radius: var(--cn-radius-md);
    font-size: var(--cn-size-sm);
    line-height: 1.5;
    margin: 0.5rem 0;
    border: 1px solid transparent;
}}

.cn-alert-error {{
    background: var(--cn-danger-bg);
    color: var(--cn-danger-fg);
    border-color: rgba(239, 68, 68, 0.35);
}}

.cn-alert-info {{
    background: var(--cn-info-bg);
    color: var(--cn-info-fg);
    border-color: rgba(59, 130, 246, 0.3);
}}

.cn-alert-warning {{
    background: var(--cn-warning-bg);
    color: var(--cn-warning-fg);
    border-color: rgba(245, 158, 11, 0.35);
}}

.cn-stat-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--cn-space-sm);
    margin: var(--cn-space-md) 0;
}}

.cn-empty-stat {{
    text-align: center;
    padding: var(--cn-space-md);
    color: var(--cn-text-muted);
    font-size: var(--cn-size-sm);
}}

.cn-empty-stat .icon {{
    font-size: 1.5rem;
    opacity: 0.45;
    margin-bottom: 0.35rem;
}}

/* Code paths in prose */
code, .stMarkdown code {{
    font-family: var(--cn-font-mono) !important;
    font-size: 0.85em !important;
}}
"""


def apply_branding(component: str = "global") -> str:
    """
    Inject consistent logo, color scheme, and font onto a named surface.

    How a component receives branding (Streamlit):
    - ``\"global\"`` — side-effect: injects CSS variables + base stylesheet once
      via ``st.markdown``; returns the active mode string.
    - ``\"chat\"`` / ``\"sidebar\"`` / ``\"diagram\"`` — returns an HTML wrapper
      opening tag that applies the shared brand class + logo chip; caller closes
      with ``</div>``.

    Always uses ``active_theme()`` (startup-loaded), never ad-hoc colors.
    """
    theme = active_theme()
    surface = (component or "global").strip().lower()

    if surface == "global":
        st.markdown(f"<style>{_global_stylesheet(theme)}</style>", unsafe_allow_html=True)
        return theme.mode

    if surface == "chat":
        return (
            f'<div class="cn-brand-chat" data-brand="{theme.brand_name}">'
            f'<div class="sidebar-brand">{theme.brand_logo} {theme.brand_name}</div>'
        )
    if surface == "sidebar":
        return (
            f'<div class="cn-brand-sidebar" data-brand="{theme.brand_name}">'
            f'<div class="sidebar-brand"><span style="color:var(--cn-teal-400)">{theme.brand_logo}</span> {theme.brand_name}</div>'
            f'<div class="sidebar-brand-sub">{theme.brand_tagline}</div>'
        )
    if surface == "diagram":
        return (
            f'<div class="cn-brand-diagram" data-brand="{theme.brand_name}">'
            f'<div class="sidebar-brand">{theme.brand_logo} Diagram</div>'
        )

    # Unknown surface → still apply global tokens (never unstyled).
    st.markdown(f"<style>{_global_stylesheet(theme)}</style>", unsafe_allow_html=True)
    return theme.mode


def boot_theme() -> ThemeTokens:
    """
    Load theme once at frontend startup.

    Resolves session preference (default dark), caches into ``_ACTIVE_THEME``,
    and injects global branding CSS.
    """
    global _ACTIVE_THEME
    mode = resolve_session_mode()
    _ACTIVE_THEME = get_theme(mode)
    apply_branding("global")
    return _ACTIVE_THEME


def render_theme_mode_toggle() -> None:
    """Sidebar light/dark toggle — session-scoped via ``set_theme_mode``."""
    current = resolve_session_mode()
    choice = st.sidebar.radio(
        "Appearance",
        options=["dark", "light"],
        index=0 if current == "dark" else 1,
        format_func=lambda m: "Dark" if m == "dark" else "Light",
        key="theme_mode_radio",
        horizontal=True,
    )
    if choice != current:
        set_theme_mode(choice)  # type: ignore[arg-type]
        st.rerun()


def widget_style_tokens() -> dict[str, str]:
    """
    Flat token map for embedded HTML widgets (voice / loading).

    Prefer this over hardcoding hex in Modules #31–#33.
    """
    t = active_theme()
    c, ty = t.colors, t.typography
    return {
        "font_family": ty.font_family,
        "accent": c.accent,
        "accent_strong": c.accent_strong,
        "text": c.text,
        "text_muted": c.text_muted,
        "text_inverse": c.text_inverse,
        "success_fg": c.success_fg,
        "border": c.border,
        "surface": c.surface,
        "danger": c.danger_fg,
        "danger_bg": c.danger_bg,
        "warning_fg": c.warning_fg,
        "info_bg": c.info_bg,
        "info_fg": c.info_fg,
        "skeleton_a": c.skeleton_a,
        "skeleton_b": c.skeleton_b,
        "navy_900": c.navy_900,
        "teal_400": c.teal_400,
        "blue_500": c.blue_500,
        "text_inverse": c.text_inverse,
    }
