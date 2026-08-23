from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.input_dock import (
    _get_file_icon,
    _truncate,
    render_input_dock,
)
from mvgeos_gui.state import AppState


def test_truncate_short() -> None:
    assert _truncate("hello", 10) == "hello"


def test_truncate_long() -> None:
    assert _truncate("hello world", 8) == "hello..."


def test_truncate_exact() -> None:
    assert _truncate("hello", 5) == "hello"


def test_get_file_icon_known() -> None:
    assert _get_file_icon(Path("test.py")) == "code"
    assert _get_file_icon(Path("style.css")) == "css"


def test_get_file_icon_unknown() -> None:
    icon = _get_file_icon(Path("unknown.xyz"))
    assert isinstance(icon, str)
    assert len(icon) > 0


@pytest.mark.asyncio
async def test_render_input_dock_smoke(user: User, tmp_path: Path) -> None:
    state = AppState(project_path=tmp_path)

    @ui.page("/test_input_dock_smoke")
    def page() -> None:
        render_input_dock(state)

    await user.open("/test_input_dock_smoke")
    await user.should_see("Ask anything")
