from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.diff_review import render_diff_modal
from mvgeos_gui.models import DiffView


def _make_diff(additions=1, deletions=0, hunks=None) -> DiffView:
    view = MagicMock(spec=DiffView)
    view.file_path = "src/a.py"
    view.status = "modified"
    view.additions = additions
    view.deletions = deletions
    view.hunks = hunks or []
    return view


@pytest.mark.asyncio
async def test_render_diff_modal_basic(user: User) -> None:
    state = MagicMock()
    state.clear_diff_selection = MagicMock()
    view = _make_diff()

    @ui.page("/test_diff_basic")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_basic")
    await user.should_see("src/a.py")


@pytest.mark.asyncio
async def test_render_diff_modal_with_hunk(user: User) -> None:
    state = MagicMock()
    line = MagicMock()
    line.line_type = "addition"
    line.content = "new"
    line.old_line_number = None
    line.new_line_number = 1
    hunk = MagicMock()
    hunk.source_start = 1
    hunk.source_length = 2
    hunk.target_start = 1
    hunk.target_length = 3
    hunk.lines = [line]
    view = _make_diff(hunks=[hunk])

    @ui.page("/test_diff_hunk")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_hunk")
    await user.should_see("src/a.py")
