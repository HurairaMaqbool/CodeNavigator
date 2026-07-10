# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #34 — shared design system (theme.py) tests."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from frontend.theme import (
    DEFAULT_THEME_MODE,
    THEME_MODE_SESSION_KEY,
    apply_branding,
    get_theme,
    resolve_session_mode,
    set_theme_mode,
    widget_style_tokens,
)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Files allowed to define the palette (theme.py) or contain only CSS-var references.
_TOKEN_SOURCE = "theme.py"


def test_get_theme_defaults_to_dark():
    theme = get_theme()
    assert theme.mode == "dark"
    assert DEFAULT_THEME_MODE == "dark"


def test_get_theme_missing_mode_falls_back_to_dark():
    assert get_theme(None).mode == "dark"
    assert get_theme("").mode == "dark"
    assert get_theme("garbage").mode == "dark"


def test_palette_is_indigo_coral_slate_concrete_hex():
    dark = get_theme("dark")
    assert dark.colors.navy_900 == "#0F172A"
    assert dark.colors.blue_500 == "#6366F1"
    assert dark.colors.teal_500 == "#F97316"
    assert "Inter" in dark.typography.font_family
    assert dark.spacing.unit == 8
    assert dark.spacing.xs == "8px"
    assert dark.spacing.huge == "64px"


def test_get_theme_is_cached_once_per_mode():
    a = get_theme("dark")
    b = get_theme("dark")
    assert a is b
    light = get_theme("light")
    assert light is not a
    assert light.mode == "light"
    assert light.colors.bg == "#F8FAFC"


def test_widget_style_tokens_expose_shared_palette():
    tokens = widget_style_tokens()
    assert tokens["blue_500"] == "#6366F1"
    assert tokens["teal_400"] == "#FB923C"
    assert "Inter" in tokens["font_family"]


def test_resolve_session_mode_defaults_dark_when_absent():
    st_mock = MagicMock()
    st_mock.session_state = {}
    with patch("frontend.theme.st", st_mock):
        assert resolve_session_mode() == "dark"


def test_set_theme_mode_persists_session_key():
    st_mock = MagicMock()
    st_mock.session_state = {}
    with patch("frontend.theme.st", st_mock):
        set_theme_mode("light")
        assert st_mock.session_state[THEME_MODE_SESSION_KEY] == "light"
        set_theme_mode("dark")
        assert st_mock.session_state[THEME_MODE_SESSION_KEY] == "dark"


def test_apply_branding_surfaces():
    st_mock = MagicMock()
    with patch("frontend.theme.st", st_mock):
        mode = apply_branding("global")
        assert mode == "dark"
        st_mock.markdown.assert_called()
        chat = apply_branding("chat")
        assert "cn-brand-chat" in chat
        assert "CodeNavigator" in chat
        side = apply_branding("sidebar")
        assert "cn-brand-sidebar" in side
        diag = apply_branding("diagram")
        assert "cn-brand-diagram" in diag


def test_no_hardcoded_hex_outside_theme_py():
    """Verify frontend modules pull tokens from theme.py (no ad-hoc hex palettes)."""
    hex_re = re.compile(r"#[0-9A-Fa-f]{6}\b")
    offenders: list[str] = []
    for path in FRONTEND_DIR.glob("*.py"):
        if path.name == _TOKEN_SOURCE:
            continue
        text = path.read_text(encoding="utf-8")
        for match in hex_re.finditer(text):
            value = match.group(0).upper()
            if value in {"#FFFFFF", "#FFF"}:
                continue
            offenders.append(f"{path.name}:{value}")
    assert offenders == [], f"Hardcoded hex outside theme.py: {offenders}"
