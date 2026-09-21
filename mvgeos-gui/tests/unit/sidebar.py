"""Unit tests for the Left Navigation Sidebar component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nicegui import app as nicegui_app
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.shell import render_shell
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
async def test_sidebar_settings_opens_modal_not_view(user: User) -> None:
    """Clicking Settings must open the app settings modal, not switch views.

    Regression test: the sidebar Settings item used to call
    set_current_view("settings"), which shell.py has no branch for, so it
    fell through to the chat view.
    """
    state = AppState(project_path=Path("C:/demo/project"), sidebar_open=True)
    state.current_user = _mock_user()
    state.set_current_view("chat")

    @ui.page("/test_sidebar_settings_modal")
    def page() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_settings_modal")
    settings_btn = user.find(marker="sidebar_nav_settings")
    assert settings_btn is not None
    settings_btn.click()
    assert state._show_app_settings is True
    assert state.current_view == "chat"


@pytest.mark.asyncio
async def test_sidebar_settings_collapsed_opens_modal(user: User) -> None:
    """Collapsed sidebar Settings icon must also open the settings modal."""
    state = AppState(project_path=Path("C:/demo/project"), sidebar_open=False)
    state.current_user = _mock_user()
    state.set_current_view("chat")

    @ui.page("/test_sidebar_settings_modal_collapsed")
    def page() -> None:
        render_sidebar(state)

    await user.open("/test_sidebar_settings_modal_collapsed")
    settings_btn = user.find(marker="sidebar_nav_settings")
    assert settings_btn is not None
    settings_btn.click()
    assert state._show_app_settings is True
    assert state.current_view == "chat"


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


def test_mobile_drawer_bootstrap_wiring() -> None:
    """Drawer bootstrap creates hamburger + scrim and toggles drawer (Major #4).

    The script is injected via ui.add_body_html and must be idempotent
    across sidebar re-renders: it guards on window.__mvgeDrawerWired,
    creates the hamburger/scrim in <body> (outside the transformed
    sidebar container so position: fixed keeps working), and closes on
    scrim click, in-drawer tap, or Escape.
    """
    from mvgeos_gui.components.sidebar import MOBILE_DRAWER_BOOTSTRAP

    assert "__mvgeDrawerWired" in MOBILE_DRAWER_BOOTSTRAP
    assert "mobile-menu-btn" in MOBILE_DRAWER_BOOTSTRAP
    assert "sidebar-scrim" in MOBILE_DRAWER_BOOTSTRAP
    assert "mobile-open" in MOBILE_DRAWER_BOOTSTRAP
    assert "Escape" in MOBILE_DRAWER_BOOTSTRAP
    assert "document.body.appendChild" in MOBILE_DRAWER_BOOTSTRAP


@pytest.mark.asyncio
async def test_sidebar_first_click_collapses_fresh_client(
    user: User, tmp_path: Path
) -> None:
    """Fresh browser (no cookie): the first chevron click visibly collapses."""
    state = AppState(project_path=tmp_path, sidebar_open=True)
    state.current_user = _mock_user()

    @ui.page("/test_sidebar_first_click")
    def page() -> None:
        nicegui_app.storage.user.pop("sidebar-collapsed", None)
        render_shell(state)

    await user.open("/test_sidebar_first_click")
    await user.should_see("+ New Conversation")
    user.find(marker="collapse_sidebar_btn").click()
    await user.should_not_see("+ New Conversation")
    assert user.find(marker="expand_sidebar_btn") is not None


@pytest.mark.asyncio
async def test_sidebar_toggle_follows_rendered_state_not_stale_cookie(
    user: User, tmp_path: Path
) -> None:
    """The chevron toggles the single source of truth (state.sidebar_open).

    If the per-browser cookie disagrees with the rendered state, the
    toggle must still move the visible state — deriving the new state
    from the cookie made the first click a no-op.
    """
    state = AppState(project_path=tmp_path, sidebar_open=False)
    state.current_user = _mock_user()

    @ui.page("/test_sidebar_stale_cookie")
    def page() -> None:
        # Stale cookie claims "expanded" while the client renders collapsed.
        nicegui_app.storage.user["sidebar-collapsed"] = False
        render_shell(state)

    await user.open("/test_sidebar_stale_cookie")
    await user.should_not_see("+ New Conversation")
    user.find(marker="expand_sidebar_btn").click()
    await user.should_see("+ New Conversation")
    assert user.find(marker="collapse_sidebar_btn") is not None


@pytest.mark.asyncio
async def test_sidebar_refreshes_on_login(user: User, tmp_path: Path) -> None:
    """Setting current_user re-renders the sidebar without a page reload."""
    state = AppState(project_path=tmp_path, sidebar_open=True)

    @ui.page("/test_sidebar_login_refresh")
    def page() -> None:
        render_shell(state)

    await user.open("/test_sidebar_login_refresh")
    await user.should_see("Sign In")
    state.current_user = _mock_user()
    state.notify()
    await user.should_see("+ New Conversation")
