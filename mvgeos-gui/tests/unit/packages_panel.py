"""Unit tests for the Packages Panel component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.packages_panel import render_packages_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_packages_panel(user: User) -> None:
    """Packages panel should render title and empty installed message."""
    state = AppState()

    @ui.page("/test_packages_panel")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_panel")
    await user.should_see("Packages")
    await user.should_see("Installed")
    await user.should_see("No packages installed")


@pytest.mark.asyncio
async def test_packages_panel_back_to_chat_button(user: User) -> None:
    """Clicking Back to Chat button should switch view to chat."""
    state = AppState()
    state.set_current_view = MagicMock()

    @ui.page("/test_packages_back_btn")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_back_btn")
    user.find("Back to Chat").click()
    state.set_current_view.assert_called_once_with("chat")
