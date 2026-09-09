"""Unit tests for the Diagnostics Panel component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.diagnostics_panel import render_diagnostics_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_diagnostics_panel(user: User) -> None:
    """Diagnostics panel should display system health and session metrics."""
    state = AppState()
    state.selected_model = "anthropic/claude-3.5-sonnet"
    state.mvge_status = "idle"
    state.active_tome_id = "tome-12345"
    state.tome_title = "Diagnostics Test Tome"
    state.total_mana_used = 1500
    state.is_channeling = False

    @ui.page("/test_diagnostics_panel")
    def page() -> None:
        render_diagnostics_panel(state)

    await user.open("/test_diagnostics_panel")
    await user.should_see("Diagnostics")
    await user.should_see("System")
    await user.should_see("claude-3.5-sonnet")
    await user.should_see("Session")
    await user.should_see("tome-12345")
    await user.should_see("Diagnostics Test Tome")
    await user.should_see("1,500")


@pytest.mark.asyncio
async def test_diagnostics_panel_back_to_chat_button(user: User) -> None:
    """Clicking Back to Chat button should switch view to chat."""
    state = AppState()
    state.set_current_view = MagicMock()

    @ui.page("/test_diagnostics_back_btn")
    def page() -> None:
        render_diagnostics_panel(state)

    await user.open("/test_diagnostics_back_btn")
    user.find("Back to Chat").click()
    state.set_current_view.assert_called_once_with("chat")
