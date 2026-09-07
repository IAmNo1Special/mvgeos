"""Unit tests for the Login Screen component."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.login_screen import render_login_screen
from mvgeos_gui.core.database import init_db
from mvgeos_gui.core.security import login_limiter
from mvgeos_gui.state import AppState


@pytest.fixture(autouse=True)
def setup_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "login_screen_test.db"
    monkeypatch.setenv("MVGEOS_DB_PATH", str(db_file))
    init_db()
    login_limiter._attempts.clear()
    login_limiter._locked_until.clear()


@pytest.mark.asyncio
async def test_login_screen_renders(user: User) -> None:
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_screen")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_screen")
    await user.should_see("Sign in to continue")
    await user.should_see("Sign In")
    await user.should_see("Default: admin / admin")


@pytest.mark.asyncio
async def test_login_screen_hidden_when_flag_false(user: User) -> None:
    state = AppState()
    state._show_login = False

    @ui.page("/test_login_hidden")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_hidden")
    await user.should_not_see("Sign in to continue")


@pytest.mark.asyncio
async def test_login_screen_validation_empty(user: User) -> None:
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_validation")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_validation")
    user.find("Sign In").click()
    await user.should_see("Enter both username and password")
