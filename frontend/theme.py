# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #34 — shared design system tokens (dark-first)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

try:
    import streamlit as st
except ImportError:  # pragma: no cover — tests patch st
    st = None  # type: ignore

DEFAULT_THEME_MODE = "dark"
THEME_MODE_SESSION_KEY = "cn_theme_mode"


@dataclass(frozen=True)
class ColorTokens:
    navy_900: str = "#0F172A"
    blue_500: str = "#6366F1"
    teal_500: str = "#F97316"
    teal_400: str = "#FB923C"
    bg: str = "#0F172A"
    text: str = "#F8FAFC"


@dataclass(frozen=True)
class TypographyTokens:
    font_family: str = "Inter, system-ui, sans-serif"
    scale_base: str = "16px"


@dataclass(frozen=True)
class SpacingTokens:
    unit: int = 8
    xs: str = "8px"
    sm: str = "16px"
    md: str = "24px"
    lg: str = "32px"
    huge: str = "64px"


@dataclass(frozen=True)
class Theme:
    mode: str
    colors: ColorTokens
    typography: TypographyTokens
    spacing: SpacingTokens


def _build_theme(mode: str) -> Theme:
    from dataclasses import replace

    colors = ColorTokens()
    if mode == "light":
        colors = replace(colors, bg="#F8FAFC", text="#0F172A")
    return Theme(mode=mode, colors=colors, typography=TypographyTokens(), spacing=SpacingTokens())


@lru_cache(maxsize=4)
def get_theme(mode: str | None = None) -> Theme:
    raw = DEFAULT_THEME_MODE if mode is None else mode
    resolved = str(raw).strip().lower()
    if resolved not in ("dark", "light"):
        resolved = DEFAULT_THEME_MODE
    return _build_theme(resolved)


def widget_style_tokens() -> dict[str, str]:
    dark = get_theme("dark")
    return {
        "navy_900": dark.colors.navy_900,
        "blue_500": dark.colors.blue_500,
        "teal_500": dark.colors.teal_500,
        "teal_400": dark.colors.teal_400,
        "bg": dark.colors.bg,
        "text": dark.colors.text,
        "font_family": dark.typography.font_family,
        "spacing_xs": dark.spacing.xs,
        "spacing_huge": dark.spacing.huge,
    }


def resolve_session_mode() -> str:
    if st is None:
        return DEFAULT_THEME_MODE
    raw = st.session_state.get(THEME_MODE_SESSION_KEY, DEFAULT_THEME_MODE)
    mode = str(raw).strip().lower()
    return mode if mode in ("dark", "light") else DEFAULT_THEME_MODE


def set_theme_mode(mode: str) -> None:
    if st is None:
        return
    st.session_state[THEME_MODE_SESSION_KEY] = mode if mode in ("dark", "light") else DEFAULT_THEME_MODE


def apply_branding(surface: str) -> str:
    mode = resolve_session_mode()
    if mode not in ("dark", "light"):
        mode = DEFAULT_THEME_MODE
    theme = get_theme(mode)
    tokens = widget_style_tokens()
    css = (
        f".cn-brand {{ font-family: {tokens['font_family']}; "
        f"color: {theme.colors.text}; background: {theme.colors.bg}; }}"
    )
    if st is not None:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    if surface == "chat":
        return f'<div class="cn-brand cn-brand-chat">CodeNavigator</div>'
    if surface == "sidebar":
        return '<div class="cn-brand cn-brand-sidebar">CodeNavigator</div>'
    if surface == "diagram":
        return '<div class="cn-brand cn-brand-diagram">CodeNavigator</div>'
    return mode
