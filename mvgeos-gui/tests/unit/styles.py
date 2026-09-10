"""Unit tests for the styles and design tokens."""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.styles import (
    CURVY_COMPOSER_CSS,
    GOOGLE_FONTS_HTML,
    VOID_THEME_CSS,
    inject_theme,
)


def test_theme_css_and_fonts_constants() -> None:
    """Validate CSS and Google Fonts strings are non-empty and well-formed."""
    assert "--bg-canvas" in VOID_THEME_CSS
    assert "fonts.googleapis.com" in GOOGLE_FONTS_HTML


def test_void_theme_palette() -> None:
    """Void theme matches the curvy composer: near-black, violet, pink."""
    assert "--bg-canvas: #000000" in VOID_THEME_CSS
    assert "--bg-surface: #08080a" in VOID_THEME_CSS
    assert "--accent-primary: #7b6cf6" in VOID_THEME_CSS
    assert "--accent-pink: #cf30aa" in VOID_THEME_CSS
    assert "#3b82f6" not in VOID_THEME_CSS
    assert "#181a20" not in VOID_THEME_CSS


def test_curvy_composer_css_omits_search_icon() -> None:
    """Curvy composer adapts uiverse input without search icon."""
    assert ".mvge-poda" in CURVY_COMPOSER_CSS
    assert ".mvge-main" in CURVY_COMPOSER_CSS
    assert ".mvge-send-btn" in CURVY_COMPOSER_CSS
    assert ".mvge-send-border" in CURVY_COMPOSER_CSS
    assert "search-icon" not in CURVY_COMPOSER_CSS


def test_curvy_glow_blur_fits_wrapper_padding() -> None:
    """Glow blur fits wrapper padding."""
    assert "filter: blur(12px);" in CURVY_COMPOSER_CSS
    assert "blur(30px)" not in CURVY_COMPOSER_CSS


def test_glow_buttons_use_young_newt_glass() -> None:
    """Primary CTAs use the young-newt glass treatment, not a flat fill."""
    assert "--highlight-color-hue: 258deg" in VOID_THEME_CSS
    assert "inset 0px 1px 1px rgba(255, 255, 255, 0.2)" in VOID_THEME_CSS
    assert "#5b3df0" not in VOID_THEME_CSS


@pytest.mark.asyncio
async def test_inject_theme(user: User) -> None:
    """inject_theme should add head HTML and CSS without error."""

    @ui.page("/test_styles")
    def page() -> None:
        inject_theme()
        ui.label("Theme Injected")

    await user.open("/test_styles")
    await user.should_see("Theme Injected")
