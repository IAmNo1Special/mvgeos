"""Unit tests for the Command Palette component."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User
from nicegui.testing.user_interaction import UserInteraction

from mvgeos_gui.components.command_palette import (
    filter_commands,
    get_palette_commands,
    render_command_palette,
    render_rename_dialog,
)
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
async def test_render_command_palette_settings_opens_modal(user: User) -> None:
    """Clicking Settings in the palette must open the settings modal, not a view.

    Regression test: the palette Settings entry used to call
    set_current_view("settings"), which shell.py has no branch for, so it
    fell through to the chat view.
    """
    state = AppState()
    state._command_palette_open = True
    state.set_current_view = MagicMock()
    state.open_app_settings = MagicMock()

    @ui.page("/test_palette_settings")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_settings")
    label = next(iter(user.find("Settings").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    state.open_app_settings.assert_called_once()
    state.set_current_view.assert_not_called()
    assert state._command_palette_open is False


@pytest.mark.asyncio
async def test_render_command_palette_opens_dialog(user: User) -> None:
    """The palette dialog must open, not just render its content hidden.

    Regression test: the dialog was constructed but .open() was never called,
    so toggling the palette (Ctrl+Shift+P, toolbar button) flipped state and
    re-rendered without anything ever appearing on screen.
    """
    state = AppState()
    state._command_palette_open = True

    @ui.page("/test_palette_dialog_open")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_dialog_open")
    dialog = next(iter(user.find(ui.dialog).elements))
    assert dialog.value is True


@pytest.mark.asyncio
async def test_palette_search_input_has_no_own_escape_handler(user: User) -> None:
    """Escape is owned by the global keyboard dispatcher (components/keyboard.py).

    A per-element keydown.escape on the search input would fire during bubble
    before the document-level handler and could trigger two actions (e.g.
    close the palette AND interrupt channeling) on a single press.
    """
    state = AppState()
    state._command_palette_open = True

    @ui.page("/test_palette_no_escape")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_no_escape")
    search_input = next(iter(user.find(ui.input).elements))
    escape_listeners = [
        v for v in search_input._event_listeners.values() if v.type == "keydown.escape"
    ]
    assert escape_listeners == []


def _command_labels(commands) -> list:
    return [c.label for c in commands]


def test_filter_commands_matches_substring_case_insensitive() -> None:
    commands = get_palette_commands()
    assert _command_labels(filter_commands(commands, "fork")) == ["Fork session"]
    assert _command_labels(filter_commands(commands, "SIDEBAR")) == ["Toggle sidebar"]
    assert "Go to Chat" in _command_labels(filter_commands(commands, "chat"))


def test_filter_commands_empty_query_returns_all() -> None:
    commands = get_palette_commands()
    expected = _command_labels(commands)
    assert _command_labels(filter_commands(commands, "")) == expected
    assert _command_labels(filter_commands(commands, "   ")) == expected


def test_filter_commands_no_match_returns_empty() -> None:
    assert filter_commands(get_palette_commands(), "zzz-no-such-command") == []


def test_session_commands_need_active_tome() -> None:
    commands = {c.label: c for c in get_palette_commands()}
    idle = AppState()
    assert commands["Fork session"].enabled(idle) is False
    assert commands["Export session"].enabled(idle) is False

    active = AppState()
    active.active_tome_id = "tome-123"
    assert commands["Fork session"].enabled(active) is True
    assert commands["Export session"].enabled(active) is True


@pytest.mark.asyncio
async def test_palette_search_filters_results(user: User) -> None:
    """Typing in the palette search box filters the command list live."""
    state = AppState()
    state._command_palette_open = True

    @ui.page("/test_palette_filter")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_filter")
    await user.should_see("New session")

    user.find(marker="palette_search_input").type("fork")

    await user.should_see("Fork session")
    await user.should_not_see("New session")


@pytest.mark.asyncio
async def test_palette_search_no_match_shows_empty_state(user: User) -> None:
    """A query matching nothing shows an explicit empty message."""
    state = AppState()
    state._command_palette_open = True

    @ui.page("/test_palette_empty")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_empty")

    user.find(marker="palette_search_input").type("zzz-no-such-command")

    await user.should_see("No commands matching")


@pytest.mark.asyncio
async def test_palette_new_session_runs_and_closes(user: User) -> None:
    """Clicking New session runs the action and closes the palette."""
    state = AppState()
    state._command_palette_open = True
    state.new_conversation = MagicMock()

    @ui.page("/test_palette_new_session")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_new_session")
    label = next(iter(user.find("New session").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    state.new_conversation.assert_called_once()
    assert state.command_palette_open is False


@pytest.mark.asyncio
async def test_palette_fork_row_not_clickable_without_active_tome(user: User) -> None:
    """Fork is visible but inert when there is no active session."""
    state = AppState()
    state._command_palette_open = True
    state.active_tome_id = None
    state.fork_tome = MagicMock()

    @ui.page("/test_palette_fork_disabled")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_fork_disabled")
    label = next(iter(user.find("Fork session").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    state.fork_tome.assert_not_called()


def test_rename_and_compact_commands_need_active_tome() -> None:
    commands = {c.label: c for c in get_palette_commands()}
    assert "Rename session" in commands
    assert "Compact session" in commands

    idle = AppState()
    assert commands["Rename session"].enabled(idle) is False
    assert commands["Compact session"].enabled(idle) is False

    active = AppState()
    active.active_tome_id = "tome-123"
    assert commands["Rename session"].enabled(active) is True
    assert commands["Compact session"].enabled(active) is True


def test_compact_command_disabled_while_channeling() -> None:
    commands = {c.label: c for c in get_palette_commands()}
    state = AppState()
    state.active_tome_id = "tome-123"
    state.is_channeling = True

    assert commands["Compact session"].enabled(state) is False


@pytest.mark.asyncio
async def test_palette_rename_row_not_clickable_without_active_tome(
    user: User,
) -> None:
    """Rename is visible but inert when there is no active session."""
    state = AppState()
    state._command_palette_open = True
    state.active_tome_id = None
    state.rename_tome = MagicMock()

    @ui.page("/test_palette_rename_disabled")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_rename_disabled")
    label = next(iter(user.find("Rename session").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    state.rename_tome.assert_not_called()


@pytest.mark.asyncio
async def test_palette_rename_opens_dialog_with_input(user: User) -> None:
    """Clicking Rename session opens a dialog prefilled with the title.

    The dialog renders from the overlay refreshable (like the settings
    modals), so the test renders it after the command flips the flag.
    """
    state = AppState()
    state._command_palette_open = True
    state.active_tome_id = "tome-123"
    state.tome_title = "Old Title"

    @ui.page("/test_palette_rename_dialog")
    def page() -> None:
        render_command_palette(state)
        render_rename_dialog(state)

    await user.open("/test_palette_rename_dialog")
    label = next(iter(user.find("Rename session").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()
    # The app re-renders overlays from the refreshable on notify;
    # render the dialog the same way, inside the client context.
    with user:
        render_rename_dialog(state)

    rename_input = user.find(marker="rename_session_input")
    await user.should_see("Rename session")
    assert rename_input is not None


@pytest.mark.asyncio
async def test_palette_rename_confirm_calls_rename_tome(user: User) -> None:
    """Submitting the rename dialog renames the active session."""
    state = AppState()
    state._command_palette_open = True
    state.active_tome_id = "tome-123"
    state.tome_title = "Old Title"
    state.rename_tome = MagicMock(return_value=True)

    @ui.page("/test_palette_rename_confirm")
    def page() -> None:
        render_command_palette(state)
        render_rename_dialog(state)

    await user.open("/test_palette_rename_confirm")
    label = next(iter(user.find("Rename session").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()
    with user:
        render_rename_dialog(state)

    rename_box = user.find(marker="rename_session_input")
    rename_box.clear()
    rename_box.type("Brand New")
    user.find(marker="rename_confirm_btn").click()

    state.rename_tome.assert_called_once_with("Brand New")


@pytest.mark.asyncio
async def test_palette_compact_runs_and_notifies(user: User) -> None:
    """Clicking Compact session compacts via the agent service and notifies.

    Notifications are captured by the NiceGUI test harness's own recorder
    (user.notify); patching ui.notify does not work because the harness
    reinstalls its recorder on every user fixture access.
    """
    state = AppState()
    state._command_palette_open = True
    state.active_tome_id = "tome-123"
    service = MagicMock()
    service.compact_active_tome = AsyncMock(return_value="Compaction completed")
    state.get_agent_service = MagicMock(return_value=service)

    @ui.page("/test_palette_compact")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_compact")
    label = next(iter(user.find("Compact session").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()
    await asyncio.sleep(0.5)

    service.compact_active_tome.assert_awaited_once_with(state)
    assert user.notify.contains("Compaction completed")
    assert state.command_palette_open is False
