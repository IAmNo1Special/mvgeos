"""Unit tests for the Command Palette component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User
from nicegui.testing.user_interaction import UserInteraction

from mvgeos_gui.components.command_palette import render_command_palette
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_command_palette_closed(user: User) -> None:
    """Command palette should not render when _command_palette_open is False."""
    state = AppState()
    state._command_palette_open = False

    @ui.page("/test_palette_closed")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_closed")
    await user.should_not_see("Quick Switcher")


@pytest.mark.asyncio
async def test_render_command_palette_open(user: User) -> None:
    """Command palette should render header, search input, and view options."""
    state = AppState()
    state._command_palette_open = True

    @ui.page("/test_palette_open")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_open")
    await user.should_see("Quick Switcher")
    await user.should_see("Chat")
    await user.should_see("Sessions")
    await user.should_see("Marketplace")
    await user.should_see("Skills")
    await user.should_see("Diagnostics")
    await user.should_see("Settings")
    await user.should_not_see("Timeline")
    await user.should_not_see("Notes")


@pytest.mark.asyncio
async def test_render_command_palette_select_view(user: User) -> None:
    """Clicking a view item should switch view and close palette."""
    state = AppState()
    state._command_palette_open = True
    state.set_current_view = MagicMock()

    @ui.page("/test_palette_select")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_select")
    label = next(iter(user.find("Sessions").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    state.set_current_view.assert_called_once_with("sessions")
    assert state._command_palette_open is False


@pytest.mark.asyncio
async def test_render_command_palette_escape_key(user: User) -> None:
    """Pressing escape on search input should close palette."""
    state = AppState()
    state._command_palette_open = True

    @ui.page("/test_palette_escape")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_escape")
    search_input = next(iter(user.find(ui.input).elements))
    listener_id = next(
        k
        for k, v in search_input._event_listeners.items()
        if v.type == "keydown.escape"
    )
    search_input._handle_event({"listener_id": listener_id, "args": None})
    assert state._command_palette_open is False
