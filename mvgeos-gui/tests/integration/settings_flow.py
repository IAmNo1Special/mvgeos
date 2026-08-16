"""Integration tests for settings modals in mvgeos-gui."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui

from mvgeos_gui.components.settings_modal import render_app_settings_modal
from mvgeos_gui.components.workspace_settings_modal import (
    render_workspace_settings_modal,
)
from mvgeos_gui.config_service import AppSettings, ConfigService
from mvgeos_gui.state import AppState


def _make_app_state(tmp_path: Path) -> AppState:
    service = ConfigService(config_dir=tmp_path)
    state = AppState()
    state._config_service = service
    return state


@pytest.mark.asyncio
async def test_app_settings_persists_to_file(tmp_path: Path) -> None:
    state = _make_app_state(tmp_path)
    state._show_app_settings = True

    @ui.page("/test_persist_app")
    def page() -> None:
        render_app_settings_modal(state)

    state.open_app_settings()
    service = ConfigService(config_dir=tmp_path)
    service.save_app_settings(AppSettings(api_key="sk-persist", mana_limit=2048))

    loaded = service.load_app_settings()
    assert loaded.api_key == "sk-persist"
    assert loaded.mana_limit == 2048


@pytest.mark.asyncio
async def test_workspace_settings_persists_to_file(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    state = _make_app_state(tmp_path)
    state.project_path = project_dir
    state._show_workspace_settings = True

    @ui.page("/test_persist_workspace")
    def page() -> None:
        render_workspace_settings_modal(state)

    state.open_workspace_settings()
    service = ConfigService(config_dir=tmp_path)
    service.save_workspace_settings(
        project_dir,
        type(
            "WorkspaceSettings",
            (),
            {
                "project_name": "test-proj",
                "spells_enabled": ["bash", "read"],
                "contemplation_level": "high",
            },
        )(),
    )

    loaded = service.load_workspace_settings(project_dir)
    assert loaded.project_name == "test-proj"
    assert loaded.contemplation_level == "high"


@pytest.mark.asyncio
async def test_settings_modal_switches_model_on_save(tmp_path: Path) -> None:
    state = _make_app_state(tmp_path)
    state._show_app_settings = True
    state.selected_model = "nvidia/nemotron-3-ultra-550b-a55b:free"

    service = ConfigService(config_dir=tmp_path)
    service.save_app_settings(AppSettings(default_model="anthropic/claude-3.5-sonnet"))

    if service.load_app_settings().default_model != state.selected_model:
        state.switch_model(service.load_app_settings().default_model)

    assert state.selected_model == "anthropic/claude-3.5-sonnet"


@pytest.mark.asyncio
async def test_open_app_settings_closes_workspace_settings(tmp_path: Path) -> None:
    state = _make_app_state(tmp_path)
    state._show_workspace_settings = True
    state.open_app_settings()
    assert state._show_app_settings is True
    assert state._show_workspace_settings is False


@pytest.mark.asyncio
async def test_open_workspace_settings_closes_app_settings(tmp_path: Path) -> None:
    state = _make_app_state(tmp_path)
    state._show_app_settings = True
    state.open_workspace_settings()
    assert state._show_workspace_settings is True
    assert state._show_app_settings is False
