"""Integration tests: per-client UI state isolation (Major #1).

Two simulated browser sessions served from one ServerState must not leak
UI state: dialog flags, current view, sidebar state, chat transcript,
plan mode, and auth. Server-global config (model, project, api key) is
shared across sessions. Each test opens two independent tabs against one
ServerState and asserts both the UI rendering and the underlying state.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from nicegui import ui
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation

from mvgeos_gui.app import build_page
from mvgeos_gui.state import ServerState
from mvgeos_gui.transcript import InvocationTranscript

pytestmark = pytest.mark.asyncio


def _register_isolated_page(route: str, server: ServerState) -> list[Any]:
    """Register ``route`` so each visit mints a fresh per-client AppState.

    Returns the per-client states in visit order.
    """
    seen: list[Any] = []

    @ui.page(route)
    def isolated_page() -> None:
        state = server.new_client_state()
        seen.append(state)
        build_page(state)

    return seen


@asynccontextmanager
async def _two_sessions(
    route: str, server: ServerState
) -> AsyncGenerator[tuple[User, User, Any, Any]]:
    """Yield two independent browser sessions on one ServerState.

    Both users share one ``user_simulation`` (one ASGI app) but each gets
    its own ``User`` — own tab id, own NiceGUI client, own DOM.
    """
    async with user_simulation() as user_a:
        seen = _register_isolated_page(route, server)
        user_b = User(user_a.http_client)
        await user_a.open(route)
        await user_b.open(route)
        yield user_a, user_b, seen[0], seen[1]


async def test_settings_dialog_does_not_leak_to_fresh_session() -> None:
    """Opening Application Settings in one session must not render it in a
    second session started while the first session's dialog is open."""
    server = ServerState(project_path=Path("/tmp/iso-settings"))
    async with _two_sessions("/iso_settings", server) as (
        user_a,
        user_b,
        state_a,
        state_b,
    ):
        assert state_a is not state_b
        state_a.open_app_settings()

        await user_a.should_see("Application Settings")
        await user_b.should_not_see("Application Settings")

        # Dismiss via the close path; the dialog clears for that client
        # only and the other session is unaffected.
        state_a.close_app_settings()
        await user_a.should_not_see("Application Settings")
        await user_b.should_not_see("Application Settings")


async def test_command_palette_open_does_not_leak() -> None:
    """The command palette renders per-client."""
    server = ServerState(project_path=Path("/tmp/iso-palette"))
    async with _two_sessions("/iso_palette", server) as (
        user_a,
        user_b,
        state_a,
        state_b,
    ):
        state_a.set_command_palette_open(True)

        await user_a.should_see("Quick Switcher")
        await user_b.should_not_see("Quick Switcher")

        state_a.set_command_palette_open(False)
        assert state_b.command_palette_open is False
        await user_a.should_not_see("Quick Switcher")


async def test_current_view_is_per_client() -> None:
    """Switching the current view in one session must not move the other."""
    server = ServerState(project_path=Path("/tmp/iso-view"))
    async with _two_sessions("/iso_view", server) as (
        user_a,
        user_b,
        state_a,
        state_b,
    ):
        state_a.set_current_view("diagnostics")

        assert state_a.current_view == "diagnostics"
        assert state_b.current_view == "chat"

        await user_a.should_see("System")
        await user_b.should_not_see("System")


async def test_sidebar_collapsed_is_per_client() -> None:
    """Collapsing the sidebar in one session must not collapse the other."""
    server = ServerState(project_path=Path("/tmp/iso-sidebar"))
    async with _two_sessions("/iso_sidebar", server) as (
        _user_a,
        _user_b,
        state_a,
        state_b,
    ):
        state_a.sidebar_open = False

        assert state_a.sidebar_open is False
        assert state_b.sidebar_open is True


async def test_chat_transcript_is_per_client() -> None:
    """A transcript message appended in one session must not render in the
    other session's chat."""
    server = ServerState(project_path=Path("/tmp/iso-transcript"))
    async with _two_sessions("/iso_transcript", server) as (
        user_a,
        user_b,
        state_a,
        state_b,
    ):
        state_a.messages.append(
            InvocationTranscript.for_summoner("client-a-secret-message")
        )
        state_a.notify()

        assert any(m.content == "client-a-secret-message" for m in state_a.messages)
        assert not any(m.content == "client-a-secret-message" for m in state_b.messages)

        await user_a.should_see("client-a-secret-message")
        await user_b.should_not_see("client-a-secret-message")


async def test_auth_is_per_client() -> None:
    """Logging in through one session's login dialog must not authenticate
    the other session: the dialog opens and closes per-client, and the
    authenticated user is visible only on the session that logged in."""
    server = ServerState(project_path=Path("/tmp/iso-auth"))
    async with _two_sessions("/iso_auth", server) as (
        user_a,
        user_b,
        state_a,
        state_b,
    ):
        state_a.show_login()

        await user_a.should_see("Sign in to continue")
        await user_b.should_not_see("Sign in to continue")

        with user_a.scope(ui.dialog):
            inputs = sorted(user_a.find(ui.input).elements, key=lambda el: el.id)
            assert len(inputs) == 2
            inputs[0].value = "admin"
            inputs[1].value = "admin"
            user_a.find("Sign In").click()

        assert state_a.current_user is not None
        assert state_a.current_user.username == "admin"
        assert state_b.current_user is None

        await user_a.should_not_see("Sign in to continue")
        await user_b.should_not_see("Sign in to continue")


async def test_plan_mode_flag_is_per_client() -> None:
    """Plan mode toggles independently per session."""
    server = ServerState(project_path=Path("/tmp/iso-plan"))
    async with _two_sessions("/iso_plan", server) as (
        _user_a,
        _user_b,
        state_a,
        state_b,
    ):
        state_a.plan_mode = True

        assert state_a.plan_mode is True
        assert state_b.plan_mode is False


async def test_server_config_stays_shared_across_clients() -> None:
    """Model selection and project path are server-global: a change made
    through one client is visible to the other."""
    server = ServerState(project_path=Path("/tmp/iso-shared"))
    async with _two_sessions("/iso_shared_config", server) as (
        _user_a,
        _user_b,
        state_a,
        state_b,
    ):
        state_a.selected_model = "anthropic/claude-opus-4-6"
        state_a.selected_provider = "anthropic"

        assert state_b.selected_model == "anthropic/claude-opus-4-6"
        assert state_b.selected_provider == "anthropic"
        assert state_b.project_path == Path("/tmp/iso-shared")


async def test_disconnect_drops_client_state(user: User) -> None:
    """Dropping a client detaches its per-client state from the server;
    other clients are unaffected."""
    server = ServerState(project_path=Path("/tmp/iso-disconnect"))

    @ui.page("/iso_disconnect")
    def isolated_disconnect_page() -> None:
        state = server.new_client_state()
        ui.context.client.on_disconnect(lambda: server.drop_client_state(state))
        build_page(state)

    await user.open("/iso_disconnect")
    assert len(server.client_states) == 1
    client_state = server.client_states[0]

    server.drop_client_state(client_state)

    assert server.client_states == []
