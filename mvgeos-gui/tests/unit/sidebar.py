"""Unit tests for the Left Navigation Sidebar component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.sidebar import render_sidebar
from mvgeos_gui.models.user import User as MvgeUser
from mvgeos_gui.models.user import UserRole
from mvgeos_gui.state import AppState


def _mock_user() -> MvgeUser:
    return MvgeUser(
        id="test-user",
        username="test",
        password_hash="mock",
        role=UserRole.USER,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_sidebar_expanded_rendering(user: User) -> None:
    """Expanded sidebar should show branding, navigation labels, and collapse button."""
    state = AppState(project_path=Path("C:/demo/project"), sidebar_open=True)
    state.current_user = _mock_user()

    @ui.page("/test_sidebar_expanded")
    def page() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_expanded")
    await user.should_see("MvgeOS")
    await user.should_see("+ New Conversation")
    await user.should_see("Home")
    await user.should_see("Chat")
    await user.should_see("Sessions")
    await user.should_see("Marketplace")
    await user.should_see("Skills")
    await user.should_see("Diagnostics")
    await user.should_see("Settings")
    # Placeholder panels were removed: they had no reason to exist.
    await user.should_not_see("Timeline")
    await user.should_not_see("Notes")
    btn = user.find(marker="collapse_sidebar_btn")
    assert btn is not None


@pytest.mark.asyncio
async def test_sidebar_collapsed_rendering(user: User) -> None:
    """Collapsed sidebar should render compact expand button and icon buttons."""
    state = AppState(project_path=Path("C:/demo/project"), sidebar_open=False)
    state.current_user = _mock_user()

    @ui.page("/test_sidebar_collapsed")
    def page() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_collapsed")
    expand_btn = user.find(marker="expand_sidebar_btn")
    assert expand_btn is not None
    new_convo_btn = user.find(marker="new_conversation_btn")
    assert new_convo_btn is not None


@pytest.mark.asyncio
async def test_sidebar_collapse_button_triggers_toggle(user: User) -> None:
    """Clicking the collapse button should call state.toggle_sidebar."""
    state = AppState(sidebar_open=True)
    state.toggle_sidebar = MagicMock()

    @ui.page("/test_sidebar_collapse_click")
    def page() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_collapse_click")
    user.find(marker="collapse_sidebar_btn").click()
    state.toggle_sidebar.assert_called_once()


@pytest.mark.asyncio
async def test_sidebar_expand_button_triggers_toggle(user: User) -> None:
    """Clicking the expand button in collapsed state calls state.toggle_sidebar."""
    state = AppState(sidebar_open=False)
    state.toggle_sidebar = MagicMock()

    @ui.page("/test_sidebar_expand_click")
    def page() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_expand_click")
    user.find(marker="expand_sidebar_btn").click()
    state.toggle_sidebar.assert_called_once()


@pytest.mark.asyncio
async def test_sidebar_sign_in_button_rendered_when_no_user(user: User) -> None:
    """When user is not logged in, Sign In button should be present in both modes."""
    state = AppState(sidebar_open=True)
    state.current_user = None

    @ui.page("/test_sidebar_signin_expanded")
    def page_expanded() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_signin_expanded")
    await user.should_see("Sign In")

    state_collapsed = AppState(sidebar_open=False)
    state_collapsed.current_user = None

    @ui.page("/test_sidebar_signin_collapsed")
    def page_collapsed() -> None:
        render_sidebar(state_collapsed)

    await user.open("/test_sidebar_signin_collapsed")
    sign_in_btn = user.find(marker="sign_in_btn")
    assert sign_in_btn is not None
