"""Unit tests for the Notes Panel component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.notes_panel import render_notes_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_notes_panel(user: User) -> None:
    """Notes panel should render title, search input, and empty state message."""
    state = AppState()

    @ui.page("/test_notes_panel")
    def page() -> None:
        render_notes_panel(state)

    await user.open("/test_notes_panel")
    await user.should_see("Notes")
    await user.should_see("No saved notes yet")


@pytest.mark.asyncio
async def test_notes_panel_back_to_chat_button(user: User) -> None:
    """Clicking Back to Chat button should switch view to chat."""
    state = AppState()
    state.set_current_view = MagicMock()

    @ui.page("/test_notes_back_btn")
    def page() -> None:
        render_notes_panel(state)

    await user.open("/test_notes_back_btn")
    user.find("Back to Chat").click()
    state.set_current_view.assert_called_once_with("chat")
