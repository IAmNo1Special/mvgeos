"""Plan mode GUI: toggle, palette action, zero-spell notice."""

from __future__ import annotations

from unittest.mock import MagicMock

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
