"""Unit tests for the styles and design tokens."""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.styles import GOOGLE_FONTS_HTML, OBSIDIAN_THEME_CSS, inject_theme


def test_theme_css_and_fonts_constants() -> None:
    """Validate CSS and Google Fonts strings are non-empty and well-formed."""
    assert "--bg-canvas" in OBSIDIAN_THEME_CSS
    assert "fonts.googleapis.com" in GOOGLE_FONTS_HTML


@pytest.mark.asyncio
async def test_inject_theme(user: User) -> None:
    """inject_theme should add head HTML and CSS without error."""

    @ui.page("/test_styles")
    def page() -> None:
        inject_theme()
        ui.label("Theme Injected")

    await user.open("/test_styles")
    await user.should_see("Theme Injected")
