"""Unit tests for the Timeline Panel component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.timeline_panel import render_timeline_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_timeline_panel(user: User) -> None:
    """Timeline panel should render activity and lineage sections."""
    state = AppState()

    @ui.page("/test_timeline_panel")
    def page() -> None:
        render_timeline_panel(state)

    await user.open("/test_timeline_panel")
    await user.should_see("Timeline")
    await user.should_see("Activity")
    await user.should_see("No recent activity")
    await user.should_see("Session Lineage")
    await user.should_see("No forked sessions yet")


@pytest.mark.asyncio
async def test_timeline_panel_back_to_chat_button(user: User) -> None:
    """Clicking Back to Chat button should switch view to chat."""
    state = AppState()
    state.set_current_view = MagicMock()

    @ui.page("/test_timeline_back_btn")
    def page() -> None:
        render_timeline_panel(state)

    await user.open("/test_timeline_back_btn")
    user.find("Back to Chat").click()
    state.set_current_view.assert_called_once_with("chat")
