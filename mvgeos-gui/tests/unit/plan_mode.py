"""Plan mode GUI: toggle, palette action, zero-spell notice."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User
from nicegui.testing.user_interaction import UserInteraction

from mvgeos_gui.components.chat_panel import render_chat_panel
from mvgeos_gui.components.command_palette import (
    get_palette_commands,
    render_command_palette,
)
from mvgeos_gui.state import AppState


def _state_with_agent(
    active_spells: list[str] | None = None,
) -> tuple[AppState, MagicMock]:
    state = AppState()
    agent = MagicMock()
    agent.enabled_spells = active_spells if active_spells is not None else ["read"]
    service = MagicMock()
    service.get_or_create_agent.return_value = agent
    state.agent_service = service
    return state, agent


def test_plan_mode_defaults_off() -> None:
    assert AppState().plan_mode is False


def test_set_plan_mode_drives_engine_and_flag() -> None:
    state, agent = _state_with_agent()
    state.set_plan_mode(True)
    agent.set_plan_mode.assert_called_once_with(True)
    assert state.plan_mode is True


def test_set_plan_mode_returns_active_spell_names() -> None:
    state, _agent = _state_with_agent(active_spells=["read", "grep"])
    assert state.set_plan_mode(True) == ["read", "grep"]


def test_toggle_plan_mode_flips() -> None:
    state, agent = _state_with_agent()
    state.toggle_plan_mode()
    assert state.plan_mode is True
    agent.set_plan_mode.assert_called_with(True)
    state.toggle_plan_mode()
    assert state.plan_mode is False
    agent.set_plan_mode.assert_called_with(False)


def test_palette_lists_toggle_plan_mode() -> None:
    assert "Toggle plan mode" in [c.label for c in get_palette_commands()]


@pytest.mark.asyncio
async def test_palette_toggle_plan_mode_flips_and_closes(user: User) -> None:
    state, _agent = _state_with_agent()
    state._command_palette_open = True

    @ui.page("/test_palette_plan_mode_toggle")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_plan_mode_toggle")
    label = next(iter(user.find("Toggle plan mode").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    assert state.plan_mode is True
    assert state.command_palette_open is False


@pytest.mark.asyncio
async def test_palette_toggle_plan_mode_warns_on_zero_spells(user: User) -> None:
    """Enabling plan mode with no read-only spells shows a warning notice.

    Notifications are captured by the NiceGUI test harness's own recorder
    (user.notify); patching ui.notify does not work because the harness
    reinstalls its recorder on every user fixture access.
    """
    state, _agent = _state_with_agent(active_spells=[])
    state._command_palette_open = True

    @ui.page("/test_palette_plan_mode_zero")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_plan_mode_zero")
    label = next(iter(user.find("Toggle plan mode").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()

    assert state.plan_mode is True
    assert user.notify.contains("no spells are marked read-only")


@pytest.mark.asyncio
async def test_toolbar_plan_mode_button_toggles_and_warns(user: User) -> None:
    """Toolbar plan-mode button flips the mode and warns on zero spells."""
    state, _agent = _state_with_agent(active_spells=[])

    @ui.page("/test_toolbar_plan_mode")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_toolbar_plan_mode")
    btn = user.find(marker="chat_toolbar_plan_mode_btn")
    assert btn is not None
    btn.click()

    assert state.plan_mode is True
    assert user.notify.contains("no spells are marked read-only")


# ---------------------------------------------------------------------------
# Major #7: plan-mode toggle without an API key must refuse cleanly instead
# of raising RuntimeError, and Enter-to-send must keep working afterwards.
# ---------------------------------------------------------------------------


def _keyless_state(tmp_path, monkeypatch) -> AppState:
    """AppState whose agent service can never resolve an API key.

    Neutralizes every key source AgentService.resolve_api_key consults so
    the test is hermetic on machines that do have a key configured.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MVGEOS_API_KEY", raising=False)
    monkeypatch.setattr(
        "mvgeos_gui.services.agent_service.load_api_key_from_auth",
        lambda: None,
    )
    return AppState(project_path=tmp_path)


def test_toggle_plan_mode_without_api_key_refuses_without_raising(
    tmp_path, monkeypatch
) -> None:
    """Toggling plan mode with no API key must not raise.

    Returns None (refused), leaves plan mode off, and creates no agent.
    """
    state = _keyless_state(tmp_path, monkeypatch)
    assert state.toggle_plan_mode() is None
    assert state.plan_mode is False
    # The refused toggle must not have created an agent as a side effect.
    with pytest.raises(RuntimeError, match="API key"):
        state.get_agent_service().get_or_create_agent(state)


def test_set_plan_mode_off_without_api_key_does_not_raise(
    tmp_path, monkeypatch
) -> None:
    """Disabling plan mode with no key and no agent is a silent no-op."""
    state = _keyless_state(tmp_path, monkeypatch)
    assert state.set_plan_mode(False) == []
    assert state.plan_mode is False


@pytest.mark.asyncio
async def test_toolbar_plan_mode_button_refuses_without_api_key(
    user: User, tmp_path, monkeypatch
) -> None:
    """Toolbar toggle with no key shows a clear refusal, not an exception."""
    state = _keyless_state(tmp_path, monkeypatch)

    @ui.page("/test_toolbar_plan_mode_no_key")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_toolbar_plan_mode_no_key")
    btn = user.find(marker="chat_toolbar_plan_mode_btn")
    btn.click()  # must not raise

    assert state.plan_mode is False
    assert user.notify.contains("API key")


@pytest.mark.asyncio
async def test_palette_plan_mode_toggle_refuses_and_closes_without_api_key(
    user: User, tmp_path, monkeypatch
) -> None:
    """Palette toggle with no key refuses cleanly and still closes the
    palette, so Enter keeps reaching the composer."""
    state = _keyless_state(tmp_path, monkeypatch)
    state._command_palette_open = True

    @ui.page("/test_palette_plan_mode_no_key")
    def page() -> None:
        render_command_palette(state)

    await user.open("/test_palette_plan_mode_no_key")
    label = next(iter(user.find("Toggle plan mode").elements))
    row = label.parent_slot.parent
    UserInteraction(user, [row], target=None).click()  # must not raise

    assert state.plan_mode is False
    assert user.notify.contains("API key")
    assert state.command_palette_open is False


@pytest.mark.asyncio
async def test_enter_to_send_still_works_after_refused_plan_mode_toggle(
    user: User, tmp_path, monkeypatch
) -> None:
    """Regression: after a refused plan-mode toggle, the send pipeline
    (what Enter drives) still delivers the message."""
    state = _keyless_state(tmp_path, monkeypatch)

    @ui.page("/test_plan_mode_enter_after_refusal")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_plan_mode_enter_after_refusal")
    user.find(marker="chat_toolbar_plan_mode_btn").click()
    assert state.plan_mode is False

    service = state.get_agent_service()
    service.run_prompt = AsyncMock()
    state.submit_prompt("hello after refused toggle")
    await user.should_see("hello after refused toggle")
