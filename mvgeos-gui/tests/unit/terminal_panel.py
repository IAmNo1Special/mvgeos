"""Unit tests for the Terminal Panel component."""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.terminal_panel import render_terminal_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_terminal_panel_closed(user: User) -> None:
    """Terminal panel should not render content when terminal_open is False."""
    state = AppState()
    state.terminal_open = False

    @ui.page("/test_terminal_closed")
    def page() -> None:
        render_terminal_panel(state)

    await user.open("/test_terminal_closed")
    await user.should_not_see("Terminal output will appear here.")


@pytest.mark.asyncio
async def test_render_terminal_panel_open(user: User) -> None:
    """Terminal panel should render labels and prompt when terminal_open is True."""
    state = AppState()
    state.terminal_open = True

    @ui.page("/test_terminal_open")
    def page() -> None:
        render_terminal_panel(state)

    await user.open("/test_terminal_open")
    await user.should_see("Terminal")
    await user.should_see("Terminal output will appear here.")
    await user.should_see("$")


@pytest.mark.asyncio
async def test_render_terminal_panel_close_button(user: User) -> None:
    """Clicking close button should toggle terminal state."""
    state = AppState()
    state.terminal_open = True

    @ui.page("/test_terminal_close_btn")
    def page() -> None:
        render_terminal_panel(state)

    await user.open("/test_terminal_close_btn")
    user.find("close").click()
    assert state.terminal_open is False
