import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.home_screen import render_home_screen
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_home_screen_empty(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)

    @ui.page("/test_home_empty")
    def page() -> None:
        render_home_screen(state)

    await user.open("/test_home_empty")
    await user.should_see("Welcome to MvgeOS")


@pytest.mark.asyncio
async def test_render_home_screen_with_tomes(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    # mock a tome entry
    from types import SimpleNamespace

    state.loaded_tomes = [
        SimpleNamespace(tome_id="abc123", title="Test Tome", relative_time="2h ago")
    ]

    @ui.page("/test_home_tomes")
    def page() -> None:
        render_home_screen(state)

    await user.open("/test_home_tomes")
    await user.should_see("Recent Sessions")


@pytest.mark.asyncio
async def test_home_screen_has_no_placeholders(user: User, tmp_path) -> None:
    """Home should not show placeholder buttons or duplicate actions."""
    state = AppState(project_path=tmp_path)

    @ui.page("/test_home_no_placeholders")
    def page() -> None:
        render_home_screen(state)

    await user.open("/test_home_no_placeholders")
    await user.should_not_see("Open Project")
    await user.should_not_see("Quick Start")
    # New Conversation is the single entry point to chat
    await user.should_see("New Conversation")
