"""Unit tests for the Workspace Settings modal component."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.workspace_settings_modal import (
    render_workspace_settings_modal,
)
from mvgeos_gui.config_service import ConfigService, WorkspaceSettings
from mvgeos_gui.state import AppState


def _make_state(
    tmp_path: Path, project_dir: Path, settings: WorkspaceSettings | None = None
) -> AppState:
    service = ConfigService(config_dir=tmp_path)
    if settings is not None:
        service.save_workspace_settings(project_dir, settings)
    state = AppState(project_path=project_dir)
    state._config_service = service
    state._show_workspace_settings = True
    return state


@pytest.mark.asyncio
async def test_workspace_settings_modal_shows_project_name(
    user: User, tmp_path: Path
) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    settings = WorkspaceSettings(project_name="my-project")
    state = _make_state(tmp_path, project_dir, settings)

    @ui.page("/test_workspace_name")
    def page() -> None:
        render_workspace_settings_modal(state)

    await user.open("/test_workspace_name")
    await user.should_see("my-project")


@pytest.mark.asyncio
async def test_workspace_settings_modal_shows_contemplation_level(
    user: User, tmp_path: Path
) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    settings = WorkspaceSettings(contemplation_level="high")
    state = _make_state(tmp_path, project_dir, settings)

    @ui.page("/test_workspace_contemplation")
    def page() -> None:
        render_workspace_settings_modal(state)

    await user.open("/test_workspace_contemplation")
    await user.should_see("high")


@pytest.mark.asyncio
async def test_workspace_settings_modal_has_save_button(
    user: User, tmp_path: Path
) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    state = _make_state(tmp_path, project_dir)

    @ui.page("/test_workspace_save")
    def page() -> None:
        render_workspace_settings_modal(state)

    await user.open("/test_workspace_save")
    await user.should_see("Save")


@pytest.mark.asyncio
async def test_workspace_settings_modal_has_cancel_button(
    user: User, tmp_path: Path
) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    state = _make_state(tmp_path, project_dir)

    @ui.page("/test_workspace_cancel")
    def page() -> None:
        render_workspace_settings_modal(state)

    await user.open("/test_workspace_cancel")
    await user.should_see("Cancel")


@pytest.mark.asyncio
async def test_workspace_settings_modal_does_not_render_when_hidden(
    user: User, tmp_path: Path
) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    state = _make_state(tmp_path, project_dir)
    state._show_workspace_settings = False

    @ui.page("/test_workspace_hidden")
    def page() -> None:
        render_workspace_settings_modal(state)

    await user.open("/test_workspace_hidden")
    await user.should_not_see("Project Settings")
