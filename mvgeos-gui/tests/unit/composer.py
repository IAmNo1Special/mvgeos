"""Unit tests for the Composer component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.composer import _render_missing_rune_badge
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_missing_rune_badge_names_rune_and_resolution(
    user: User,
) -> None:
    """The amber badge must name the missing rune and how to resolve it."""
    state = AppState()
    state.selected_realm = "openrouter"
    state.is_rune_installed = MagicMock(return_value=False)  # type: ignore[method-assign]

    @ui.page("/test_composer_missing_rune")
    def page() -> None:
        _render_missing_rune_badge(state)

    await user.open("/test_composer_missing_rune")
    await user.should_see("Missing rune: openrouter-realm")
    await user.should_see("Install openrouter-realm from the Marketplace")


@pytest.mark.asyncio
async def test_missing_rune_badge_click_opens_marketplace(user: User) -> None:
    """Clicking the badge navigates to the Marketplace view."""
    state = AppState()
    state.selected_realm = "openrouter"
    state.is_rune_installed = MagicMock(return_value=False)  # type: ignore[method-assign]
    state.set_current_view = MagicMock()  # type: ignore[method-assign]

    @ui.page("/test_composer_missing_rune_click")
    def page() -> None:
        _render_missing_rune_badge(state)

    await user.open("/test_composer_missing_rune_click")
    user.find(marker="missing_rune_badge").click()
    state.set_current_view.assert_called_once_with("packages")


@pytest.mark.asyncio
async def test_missing_rune_badge_hidden_when_rune_installed(
    user: User,
) -> None:
    """No badge when the rune is installed."""
    state = AppState()
    state.selected_realm = "openrouter"
    state.is_rune_installed = MagicMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_composer_rune_installed")
    def page() -> None:
        _render_missing_rune_badge(state)

    await user.open("/test_composer_rune_installed")
    await user.should_not_see("Missing rune")


@pytest.mark.asyncio
async def test_missing_rune_badge_hidden_for_other_realm(user: User) -> None:
    """No badge when the OpenRouter realm is not selected."""
    state = AppState()
    state.selected_realm = "ollama"
    state.is_rune_installed = MagicMock(return_value=False)  # type: ignore[method-assign]

    @ui.page("/test_composer_other_realm")
    def page() -> None:
        _render_missing_rune_badge(state)

    await user.open("/test_composer_other_realm")
    await user.should_not_see("Missing rune")
