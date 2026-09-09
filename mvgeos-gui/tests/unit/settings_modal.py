"""Unit tests for the Application Settings modal component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.settings_modal import render_app_settings_modal
from mvgeos_gui.services.config_service import AppSettings, ConfigService
from mvgeos_gui.state import AppState


def _make_state(tmp_path: Path, settings: AppSettings | None = None) -> AppState:
    service = ConfigService(config_dir=tmp_path)
    if settings is not None:
        service.save_app_settings(settings)
    state = AppState()
    state._config_service = service
    state._show_app_settings = True
    return state


@pytest.mark.asyncio
async def test_app_settings_modal_shows_api_key_field(
    user: User, tmp_path: Path
) -> None:
    settings = AppSettings(api_key="sk-existing")
    state = _make_state(tmp_path, settings)

    @ui.page("/test_settings_modal")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_modal")
    await user.should_see("sk-existing")


@pytest.mark.asyncio
async def test_app_settings_modal_shows_model_selector(
    user: User, tmp_path: Path
) -> None:
    state = _make_state(tmp_path)

    @ui.page("/test_settings_model")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_model")
    await user.should_see("Default Model")


@pytest.mark.asyncio
async def test_app_settings_modal_shows_mana_limit(user: User, tmp_path: Path) -> None:
    settings = AppSettings(mana_limit=8192)
    state = _make_state(tmp_path, settings)

    @ui.page("/test_settings_mana")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_mana")
    await user.should_see("8192")


@pytest.mark.asyncio
async def test_app_settings_modal_shows_theme_selector(
    user: User, tmp_path: Path
) -> None:
    state = _make_state(tmp_path)

    @ui.page("/test_settings_theme")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_theme")
    await user.should_see("Theme")


@pytest.mark.asyncio
async def test_app_settings_modal_has_save_button(user: User, tmp_path: Path) -> None:
    state = _make_state(tmp_path)

    @ui.page("/test_settings_save")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_save")
    await user.should_see("Save")


@pytest.mark.asyncio
async def test_app_settings_modal_has_cancel_button(user: User, tmp_path: Path) -> None:
    state = _make_state(tmp_path)

    @ui.page("/test_settings_cancel")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_cancel")
    await user.should_see("Cancel")


@pytest.mark.asyncio
async def test_app_settings_modal_save_success(user: User, tmp_path: Path) -> None:
    """Clicking Save should persist settings and hide modal."""
    state = _make_state(tmp_path)

    @ui.page("/test_settings_save_action")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_save_action")
    api_input = next(iter(user.find(marker="api_key_input").elements))
    api_input.set_value("sk-new-key")

    user.find("Save").click()
    assert state._show_app_settings is False
    saved = state._config_service.load_app_settings()
    assert saved.api_key == "sk-new-key"


@pytest.mark.asyncio
async def test_app_settings_modal_save_switches_model(
    user: User, tmp_path: Path
) -> None:
    """If default_model changes, switch_model should be invoked."""
    state = _make_state(tmp_path)
    state.selected_model = "different-model"
    state.switch_model = MagicMock()

    @ui.page("/test_settings_switch_model")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_switch_model")
    user.find("Save").click()
    state.switch_model.assert_called_once()


@pytest.mark.asyncio
async def test_app_settings_modal_save_invalid_mana_limit(
    user: User, tmp_path: Path
) -> None:
    """Invalid mana limit should show notification and not save."""
    state = _make_state(tmp_path)

    @ui.page("/test_settings_invalid_mana")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_invalid_mana")
    mana_input = next(iter(user.find(marker="mana_limit_input").elements))
    mana_input.set_value("-500")

    user.find("Save").click()
    assert state._show_app_settings is True
    await user.should_see("Invalid mana limit: must be a positive integer")


@pytest.mark.asyncio
async def test_app_settings_modal_save_invalid_temperature(
    user: User, tmp_path: Path
) -> None:
    """Temperature outside 0.0-2.0 should show notification and not save."""
    state = _make_state(tmp_path)

    @ui.page("/test_settings_invalid_temp")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_invalid_temp")
    temp_input = next(iter(user.find(marker="temperature_input").elements))
    temp_input.set_value("3.5")

    user.find("Save").click()
    assert state._show_app_settings is True
    await user.should_see("Invalid temperature: must be between 0.0 and 2.0")


@pytest.mark.asyncio
async def test_app_settings_modal_cancel_action(user: User, tmp_path: Path) -> None:
    """Closing the dialog should invoke _on_close and hide modal."""
    state = _make_state(tmp_path)

    @ui.page("/test_settings_cancel_action")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_cancel_action")
    dialog = next(iter(user.find(ui.dialog).elements))
    listener_id = next(
        k for k, v in dialog._event_listeners.items() if v.type == "close"
    )
    dialog._handle_event({"listener_id": listener_id, "args": None})
    assert state._show_app_settings is False


@pytest.mark.asyncio
async def test_app_settings_modal_does_not_render_when_hidden(
    user: User, tmp_path: Path
) -> None:
    """When _show_app_settings is False, modal should not render."""
    state = _make_state(tmp_path)
    state._show_app_settings = False

    @ui.page("/test_settings_hidden")
    def page() -> None:
        render_app_settings_modal(state)

    await user.open("/test_settings_hidden")
    await user.should_not_see("Application Settings")
