"""Unit tests for the Status Bar component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.status_bar import render_status_bar
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_status_bar_idle(user: User) -> None:
    """Status bar should display MvgeOS label, active model, and mana used."""
    state = AppState()
    state.selected_model = "openrouter/auto"
    state.total_mana_used = 2500
    state.is_channeling = False

    @ui.page("/test_status_bar_idle")
    def page() -> None:
        render_status_bar(state)

    await user.open("/test_status_bar_idle")
    await user.should_see("MvgeOS")
    await user.should_see("auto")
    await user.should_see("2,500 Mana")
    await user.should_not_see("Channeling...")


@pytest.mark.asyncio
async def test_render_status_bar_channeling(user: User) -> None:
    """Status bar should show channeling indicator when is_channeling is True."""
    state = AppState()
    state.is_channeling = True

    @ui.page("/test_status_bar_chan")
    def page() -> None:
        render_status_bar(state)

    await user.open("/test_status_bar_chan")
    await user.should_see("Channeling...")


@pytest.mark.asyncio
async def test_render_status_bar_toggle_buttons(user: User) -> None:
    """Toggle buttons in status bar should call their corresponding state toggles."""
    state = AppState()
    state.toggle_terminal = MagicMock()
    state.toggle_review = MagicMock()
    state.toggle_sidebar = MagicMock()

    @ui.page("/test_status_bar_toggles")
    def page() -> None:
        render_status_bar(state)

    await user.open("/test_status_bar_toggles")
    user.find(marker="toggle_terminal_btn").click()
    state.toggle_terminal.assert_called_once()

    user.find(marker="toggle_review_btn").click()
    state.toggle_review.assert_called_once()

    user.find(marker="toggle_sidebar_btn").click()
    state.toggle_sidebar.assert_called_once()


@pytest.mark.asyncio
async def test_render_status_bar_review_open_and_sidebar_closed(user: User) -> None:
    state = AppState()
    state.review_open = True
    state.sidebar_open = False
    state.selected_model = ""
    state.total_mana_used = 0

    @ui.page("/test_status_bar_alt_state")
    def page() -> None:
        render_status_bar(state)

    await user.open("/test_status_bar_alt_state")
    await user.should_see("MvgeOS")
