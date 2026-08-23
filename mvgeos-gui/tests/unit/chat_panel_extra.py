from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.chat_panel import render_chat_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_chat_panel_shows_files_side_panel(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.chat_side_panel = "files"

    @ui.page("/test_chat_files")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_files")
    await user.should_see("Files")


@pytest.mark.asyncio
async def test_chat_panel_shows_diff_side_panel(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.chat_side_panel = "diff"
    # mock diff view
    state.get_selected_diff_view = MagicMock(return_value=None)

    @ui.page("/test_chat_diff")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_diff")
    await user.should_see("Diff")
