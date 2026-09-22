"""Unit tests for the Login Screen component."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nicegui import context, ui
from nicegui.elements.input import Input
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
    await user.should_not_see("Default: admin / admin")


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


@pytest.mark.asyncio
async def test_login_screen_not_persistent(user: User) -> None:
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_not_persistent")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_not_persistent")
    dialogs = list(user.find(ui.dialog).elements)
    assert len(dialogs) > 0
    dialog = dialogs[0]
    assert "persistent" not in dialog._props
    assert "maximized" not in dialog._props


@pytest.mark.asyncio
async def test_login_screen_close_button(user: User) -> None:
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_close_btn")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_close_btn")
    close_btn = user.find(marker="close_login_btn")
    close_btn.click()
    assert state._show_login is False


@pytest.mark.asyncio
async def test_login_screen_successful_login(user: User) -> None:
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_success")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_success")
    inputs = sorted(user.find(ui.input).elements, key=lambda el: el.id)
    assert len(inputs) >= 2
    inputs[0].value = "admin"
    inputs[1].value = "admin"
    user.find("Sign In").click()
    assert state.current_user is not None
    assert state.current_user.username == "admin"
    assert state._show_login is False


@pytest.mark.asyncio
async def test_login_screen_hides_app_settings(user: User) -> None:
    state = AppState()
    state._show_login = True
    state._show_app_settings = True

    @ui.page("/test_login_hides_settings")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_hides_settings")
    assert state._show_app_settings is False


@pytest.mark.asyncio
async def test_login_screen_locked_account(user: User) -> None:
    state = AppState()
    state._show_login = True
    login_limiter._locked_until["locked_user"] = time.time() + 100

    @ui.page("/test_login_locked")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_locked")
    inputs = sorted(user.find(ui.input).elements, key=lambda el: el.id)
    inputs[0].value = "locked_user"
    inputs[1].value = "pass"
    user.find("Sign In").click()
    await user.should_see("Too many attempts. Try again later.")


@pytest.mark.asyncio
async def test_login_screen_invalid_credentials(user: User) -> None:
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_invalid")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_invalid")
    inputs = sorted(user.find(ui.input).elements, key=lambda el: el.id)
    inputs[0].value = "admin"
    inputs[1].value = "wrongpass"
    user.find("Sign In").click()
    await user.should_see("Invalid username or password")


@pytest.mark.asyncio
async def test_login_screen_exception_handling(user: User) -> None:
    state = AppState()
    state._show_login = True
    mock_auth = MagicMock()
    mock_auth.login.side_effect = RuntimeError("DB error")
    state._auth_service = mock_auth

    @ui.page("/test_login_error")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_error")
    inputs = sorted(user.find(ui.input).elements, key=lambda el: el.id)
    inputs[0].value = "admin"
    inputs[1].value = "admin"
    user.find("Sign In").click()
    await user.should_see("Login error: DB error")


@pytest.mark.asyncio
async def test_login_screen_password_enter_submits(user: User) -> None:
    """B-7: pressing Enter in the password field submits the login."""
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_enter")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_enter")
    inputs = sorted(user.find(ui.input).elements, key=lambda el: el.id)
    inputs[0].value = "admin"
    inputs[1].value = "admin"
    password_input = inputs[1]
    listener_id = next(
        k
        for k, v in password_input._event_listeners.items()
        if v.type == "keydown.enter"
    )
    password_input._handle_event({"listener_id": listener_id, "args": None})
    assert state.current_user is not None
    assert state.current_user.username == "admin"
    assert state._show_login is False


@pytest.mark.asyncio
async def test_login_screen_shows_no_credential_hint(user: User) -> None:
    """C28: the login form must not advertise default credentials."""
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_no_hint")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_no_hint")
    await user.should_not_see("Default: admin / admin")
    await user.should_not_see("admin / admin")


# ---------------------------------------------------------------------------
# Floating label / placeholder overlap
# ---------------------------------------------------------------------------


def _inputs_without_label_placeholder_overlap(client: object) -> list[str]:
    """Names of inputs that set both a floating label and a placeholder.

    Reads the element prop mapping directly: NiceGUI's public prop getter
    (``get_computed_prop``) requires live browser JavaScript and is
    unusable in the in-process test harness, so this is the narrowest
    hook that detects the overlap regression.
    """
    elements = getattr(client, "elements", {})
    bad: list[str] = []
    for element in elements.values():
        if isinstance(element, Input):
            props = element._props  # noqa: SLF001 - no public sync accessor
            if props.get("label") and props.get("placeholder"):
                bad.append(str(props.get("label")))
    return bad


@pytest.mark.asyncio
async def test_login_inputs_do_not_overlap_labels_and_placeholders(
    user: User,
) -> None:
    """Sign-in inputs must use caption labels, not floating label+placeholder."""
    state = AppState()
    state._show_login = True
    captured: dict[str, object] = {}

    @ui.page("/test_login_no_overlap")
    def page() -> None:
        render_login_screen(state)
        captured["client"] = context.client

    await user.open("/test_login_no_overlap")
    assert captured["client"] is not None
    assert _inputs_without_label_placeholder_overlap(captured["client"]) == []


@pytest.mark.asyncio
async def test_login_fields_still_have_visible_captions(user: User) -> None:
    """The caption labels above the sign-in inputs must remain visible."""
    state = AppState()
    state._show_login = True

    @ui.page("/test_login_captions")
    def page() -> None:
        render_login_screen(state)

    await user.open("/test_login_captions")
    await user.should_see("Username")
    await user.should_see("Password")
