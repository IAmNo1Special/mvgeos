"""Integration tests for 3-column obsidian shell layout and components."""

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.app import build_page, init_app
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_full_shell_layout_rendering(user: User) -> None:
    """Verify 3-column shell elements rendered correctly."""
    state = AppState(project_path=Path("C:/demo/my-project"))

    @ui.page("/test_shell_render")
    def page() -> None:
        build_page(state)

    await user.open("/test_shell_render")

    # Left sidebar branding and action
    await user.should_see("Antigravity")
    await user.should_see("New Conversation")

    # Center header breadcrumb
    await user.should_see("my-project")
    await user.should_see("Open IDE")

    # Empty state centered project switcher
    await user.should_see("Quick Start")
    await user.should_see("New Project")
    await user.should_see("No Project")

    # Right Inspector accordions
    await user.should_see("Context")
    await user.should_see("Subagents")
    await user.should_see("Files Changed")
    await user.should_see("Artifacts")
    await user.should_see("Skills Used")
    await user.should_see("Uploads")
    await user.should_see("Background Tasks")


@pytest.mark.asyncio
async def test_sidebar_toggle_interaction(user: User) -> None:
    """Verify toggling left sidebar expansion state."""
    state = AppState()

    @ui.page("/test_sidebar_toggle")
    def page() -> None:
        build_page(state)

    await user.open("/test_sidebar_toggle")
    assert state.sidebar_expanded is True

    # Click toggle sidebar button
    user.find("toggle_sidebar_btn").click()
    assert state.sidebar_expanded is False

    user.find("toggle_sidebar_btn").click()
    assert state.sidebar_expanded is True


@pytest.mark.asyncio
async def test_inspector_toggle_interaction(user: User) -> None:
    """Verify toggling inspector panel expansion state."""
    state = AppState()

    @ui.page("/test_inspector_toggle")
    def page() -> None:
        build_page(state)

    await user.open("/test_inspector_toggle")
    assert state.inspector_expanded is True

    # Click toggle inspector button
    user.find("toggle_inspector_btn").click()
    assert state.inspector_expanded is False

    user.find("toggle_inspector_btn").click()
    assert state.inspector_expanded is True


@pytest.mark.asyncio
async def test_new_conversation_button_resets_state(user: User) -> None:
    """Verify clicking '+ New Conversation' resets conversation state."""
    state = AppState()
    state.active_tome_id = "tome-99"
    state.tome_title = "Existing session"

    @ui.page("/test_new_convo_btn")
    def page() -> None:
        build_page(state)

    await user.open("/test_new_convo_btn")
    user.find("new_conversation_btn").click()

    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"


@pytest.mark.asyncio
async def test_project_picker_selection(user: User) -> None:
    """Verify switching projects from the empty state project picker."""
    state = AppState(project_path=Path("C:/demo/project-a"))
    proj_b = Path("C:/demo/project-b")
    state.add_recent_project(proj_b)

    @ui.page("/test_project_picker")
    def page() -> None:
        build_page(state)

    await user.open("/test_project_picker")
    await user.should_see("project-a")

    # Select project-b
    state.set_project(proj_b)
    assert state.project_path == proj_b


@pytest.mark.asyncio
async def test_collapsed_panels_rendering(user: User) -> None:
    """Verify initial rendering when sidebar and inspector are collapsed."""
    state = AppState(sidebar_expanded=False, inspector_expanded=False)

    @ui.page("/test_collapsed")
    def page() -> None:
        build_page(state)

    await user.open("/test_collapsed")
    assert state.sidebar_expanded is False
    assert state.inspector_expanded is False


@pytest.mark.asyncio
async def test_channeling_input_dock(user: User) -> None:
    """Verify input dock state while channeling and stopping channeling."""
    state = AppState(is_channeling=True)

    @ui.page("/test_channeling")
    def page() -> None:
        build_page(state)

    await user.open("/test_channeling")
    assert state.is_channeling is True


@pytest.mark.asyncio
async def test_init_app_registers_index(user: User) -> None:
    """Verify init_app registers the root index page properly."""
    state = AppState(project_path=Path("C:/demo/init-project"))
    app_state = init_app(state)
    assert app_state == state

    await user.open("/")
    await user.should_see("init-project")
