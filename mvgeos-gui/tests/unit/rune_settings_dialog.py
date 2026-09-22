"""Unit tests for the per-rune settings dialog."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.rune_settings_dialog import render_rune_settings_dialog
from mvgeos_gui.state import AppState


def _minimal_rune(**overrides: Any) -> dict[str, Any]:
    info: dict[str, Any] = {"name": "test-rune", "version": "1.0.0"}
    info.update(overrides)
    return info


@pytest.mark.asyncio
async def test_rune_settings_dialog_saves_without_description_or_path(
    user: User,
) -> None:
    """Save persists the enabled flag and fires on_saved when metadata is absent."""
    state = AppState()
    saved: list[bool] = []

    async def fake_set_enabled(name: str, enabled: bool) -> bool:
        assert name == "test-rune"
        assert enabled is True
        return True

    state.set_rune_enabled_async = fake_set_enabled  # type: ignore[method-assign]

    async def on_saved() -> None:
        saved.append(True)

    @ui.page("/test_rune_settings_save")
    def page() -> None:
        render_rune_settings_dialog(state, _minimal_rune(), on_saved)

    await user.open("/test_rune_settings_save")
    user.find("rune_settings_save_btn").click()
    await user.should_see("test-rune enabled.")
    assert saved == [True]


@pytest.mark.asyncio
async def test_rune_settings_dialog_save_failure_notifies(user: User) -> None:
    """A failed persist shows a negative notification and skips on_saved."""
    state = AppState()
    state.set_rune_enabled_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    saved: list[bool] = []

    async def on_saved() -> None:
        saved.append(True)

    @ui.page("/test_rune_settings_save_failure")
    def page() -> None:
        render_rune_settings_dialog(state, _minimal_rune(), on_saved)

    await user.open("/test_rune_settings_save_failure")
    user.find("rune_settings_save_btn").click()
    await user.should_see("Failed to save test-rune settings.")
    assert saved == []
