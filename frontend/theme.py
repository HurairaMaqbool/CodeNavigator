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
    # Sora for brand presence; DM Sans for readable UI copy (not Inter/system).
    font_family="'DM Sans', 'Sora', sans-serif",
    font_mono="'JetBrains Mono', 'Consolas', monospace",
    font_import_url=(
        "https://fonts.googleapis.com/css2?"
        "family=Sora:wght@500;600;700&"
        "family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;"
        "1,9..40,400&family=JetBrains+Mono:wght@400;500;600&display=swap"
    ),
    size_xs="0.75rem",
    size_sm="0.875rem",
    size_base="1rem",
    size_lg="1.125rem",
    size_xl="1.25rem",
    size_2xl="1.5rem",
    size_3xl="1.875rem",
    size_display="2.75rem",
    weight_regular=400,
    weight_medium=500,
    weight_semibold=600,
    weight_bold=700,
)

_SPACING = SpacingTokens(
    unit=4,
    xs="4px",
    sm="8px",
    md="12px",
    lg="16px",
    xl="24px",
    xxl="32px",
    xxxl="48px",
    huge="64px",
    radius_sm="10px",
    radius_md="14px",
    radius_lg="20px",
    radius_pill="999px",
    max_content_width="1180px",
)

# Refined navy / blue / teal — deep ink canvas, teal accent, blue action.
_DARK_COLORS = ColorTokens(
    navy_900="#0B1D36",
    navy_800="#12263A",
    navy_700="#1A3655",
    blue_600="#1D4ED8",
    blue_500="#2563EB",
    blue_400="#3B82F6",
    teal_500="#0D9488",
    teal_400="#2DD4BF",
    bg="#071525",
    surface="#0E2138",
    surface_elevated="#152A45",
    border="#243B55",
    text="#F1F5F9",
    text_muted="#94A3B8",
    text_inverse="#0B1D36",
    success_bg="#0A3D32",
    success_fg="#5EEAD4",
    warning_bg="#4A3208",
    warning_fg="#FBBF24",
    danger_bg="#4C1515",
    danger_fg="#FCA5A5",
    info_bg="#132A4A",
    info_fg="#93C5FD",
    accent="#2DD4BF",
    accent_strong="#2563EB",
    skeleton_a="#152A45",
    skeleton_b="#243B55",
    hero_gradient=(
        "radial-gradient(1200px 480px at 12% -10%, rgba(45,212,191,0.28), transparent 55%),"
        "radial-gradient(900px 420px at 88% 0%, rgba(37,99,235,0.32), transparent 50%),"
        "linear-gradient(145deg, #071525 0%, #0B1D36 42%, #12263A 100%)"
    ),
    sidebar_gradient="linear-gradient(180deg, #06111F 0%, #0B1D36 48%, #0E2138 100%)",
)

_LIGHT_COLORS = ColorTokens(
    navy_900="#0B1D36",
    navy_800="#12263A",
    navy_700="#1A3655",
    blue_600="#1D4ED8",
    blue_500="#2563EB",
    blue_400="#3B82F6",
    teal_500="#0D9488",
    teal_400="#14B8A6",
    bg="#F4F7FB",
    surface="#FFFFFF",
    surface_elevated="#FFFFFF",
    border="#D5DEEA",
    text="#0B1D36",
    text_muted="#5B6B7C",
    text_inverse="#FFFFFF",
    success_bg="#D1FAE5",
    success_fg="#065F46",
    warning_bg="#FEF3C7",
    warning_fg="#92400E",
    danger_bg="#FEE2E2",
    danger_fg="#991B1B",
    info_bg="#DBEAFE",
    info_fg="#1E40AF",
    accent="#0D9488",
    accent_strong="#2563EB",
    skeleton_a="#E2E8F0",
    skeleton_b="#F1F5F9",
    hero_gradient=(
        "radial-gradient(1000px 420px at 8% -20%, rgba(13,148,136,0.22), transparent 55%),"
        "radial-gradient(800px 380px at 92% 0%, rgba(37,99,235,0.20), transparent 50%),"
        "linear-gradient(145deg, #0B1D36 0%, #123A5C 48%, #0D9488 100%)"
    ),
    sidebar_gradient="linear-gradient(180deg, #06111F 0%, #0B1D36 55%, #12263A 100%)",
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

/* Primary actions */
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {{
    background: linear-gradient(135deg, var(--cn-blue-500), var(--cn-teal-500)) !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    border-radius: var(--cn-radius-sm) !important;
    box-shadow: 0 8px 20px rgba(37, 99, 235, 0.28);
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
    font-size: 0.78rem;
    padding: 0.35rem 0.7rem;
    border-radius: var(--cn-radius-pill);
    background: rgba(37, 99, 235, 0.12);
    border: 1px solid rgba(37, 99, 235, 0.28);
    color: var(--cn-info-fg);
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
