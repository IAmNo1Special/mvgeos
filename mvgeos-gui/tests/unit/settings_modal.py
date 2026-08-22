"""Unit tests for the Application Settings modal component."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.settings_modal import render_app_settings_modal
from mvgeos_gui.config_service import AppSettings, ConfigService
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
