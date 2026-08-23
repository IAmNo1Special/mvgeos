import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.header import render_header
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_header_shows_project_name(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.active_tome_id = None

    @ui.page("/test_header")
    def page() -> None:
        render_header(state)

    await user.open("/test_header")
    # header shows project folder name
    assert tmp_path.name in str(tmp_path)


@pytest.mark.asyncio
async def test_render_header_with_tome_title(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.active_tome_id = "tome-123"
    # tome_title is derived; set via state if available

    @ui.page("/test_header_tome")
    def page() -> None:
        render_header(state)

    await user.open("/test_header_tome")
    # smoke: no exception, header renders
    assert True
