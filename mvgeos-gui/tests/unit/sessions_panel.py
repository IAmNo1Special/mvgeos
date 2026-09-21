import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.sessions_panel import render_sessions_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_sessions_empty(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)

    @ui.page("/test_sessions_empty")
    def page() -> None:
        render_sessions_panel(state)

    await user.open("/test_sessions_empty")
    await user.should_see("Sessions")


@pytest.mark.asyncio
async def test_render_sessions_with_tome(user: User, tmp_path) -> None:
    from types import SimpleNamespace

    state = AppState(project_path=tmp_path)
    state.loaded_tomes = [
        SimpleNamespace(
            tome_id="t1",
            title="My Tome",
            relative_time="1h ago",
            git_branch="main",
            is_active=True,
        )
    ]

    @ui.page("/test_sessions_tome")
    def page() -> None:
        render_sessions_panel(state)

    await user.open("/test_sessions_tome")
    await user.should_see("My Tome")


@pytest.mark.asyncio
async def test_sessions_search_filters_list(user: User, tmp_path) -> None:
    """Typing in the search field should filter the session list."""
    from types import SimpleNamespace

    state = AppState(project_path=tmp_path)
    state.loaded_tomes = [
        SimpleNamespace(
            tome_id="t1",
            title="Alpha Session",
            relative_time="1h ago",
            git_branch="main",
            is_active=True,
        ),
        SimpleNamespace(
            tome_id="t2",
            title="Beta Session",
            relative_time="2h ago",
            git_branch="main",
            is_active=False,
        ),
    ]

    @ui.page("/test_sessions_search")
    def page() -> None:
        render_sessions_panel(state)

    await user.open("/test_sessions_search")
    await user.should_see("Alpha Session")
    await user.should_see("Beta Session")

    # Type in the search field
    search = user.find(marker="sessions_search_input")
    search.type("Alpha")
    await user.should_see("Alpha Session")
    await user.should_not_see("Beta Session")


@pytest.mark.asyncio
async def test_new_session_button_navigates_to_chat_with_toast(
    user: User, tmp_path
) -> None:
    """Minor C25: NEW SESSION must give visible feedback -- navigate to Chat
    and show a toast -- instead of a silent server-side reset."""
    from unittest.mock import MagicMock

    state = AppState(project_path=tmp_path)
    state.set_current_view = MagicMock()  # type: ignore[method-assign]

    @ui.page("/test_sessions_new_feedback")
    def page() -> None:
        render_sessions_panel(state)

    await user.open("/test_sessions_new_feedback")
    user.find("New Session").click()

    state.set_current_view.assert_called_once_with("chat")
    assert user.notify.contains("New session")
