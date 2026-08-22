"""Unit tests for the Diff Review modal component."""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.diff_review import render_diff_modal
from mvgeos_gui.models import DiffHunk, DiffLine, DiffView
from mvgeos_gui.state import AppState


def _make_diff_view(path: str = "src/main.py") -> DiffView:
    return DiffView(
        file_path=path,
        status="modified",
        hunks=[
            DiffHunk(
                source_start=1,
                source_length=3,
                target_start=1,
                target_length=4,
                lines=[
                    DiffLine(
                        content="# header\n",
                        line_type="context",
                        old_line_number=1,
                        new_line_number=1,
                    ),
                    DiffLine(
                        content="+import os\n",
                        line_type="addition",
                        old_line_number=None,
                        new_line_number=2,
                    ),
                    DiffLine(
                        content="-print('hello')\n",
                        line_type="deletion",
                        old_line_number=2,
                        new_line_number=None,
                    ),
                    DiffLine(
                        content="+print('hello world')\n",
                        line_type="addition",
                        old_line_number=None,
                        new_line_number=3,
                    ),
                ],
            )
        ],
        additions=2,
        deletions=1,
    )


@pytest.mark.asyncio
async def test_render_diff_review_modal_shows_file_path(user: User) -> None:
    """Verify Diff Review modal displays the reviewed file path."""
    view = _make_diff_view()
    state = AppState()
    state._selected_diff_path = view.file_path

    @ui.page("/test_diff_modal")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_modal")
    await user.should_see("src/main.py")


@pytest.mark.asyncio
async def test_render_diff_review_modal_shows_change_counts(user: User) -> None:
    """Verify Diff Review modal displays + and - line counts."""
    view = _make_diff_view()
    state = AppState()
    state._selected_diff_path = view.file_path

    @ui.page("/test_diff_counts")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_counts")
    await user.should_see("+2")
    await user.should_see("-1")


@pytest.mark.asyncio
async def test_render_diff_review_modal_shows_diff_lines(user: User) -> None:
    """Verify Diff Review modal renders diff hunk content."""
    view = _make_diff_view()
    state = AppState()
    state._selected_diff_path = view.file_path

    @ui.page("/test_diff_lines")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_lines")
    await user.should_see("import os")
    await user.should_see("print('hello world')")


@pytest.mark.asyncio
async def test_render_diff_review_modal_has_view_toggle(user: User) -> None:
    """Verify Diff Review modal includes a view mode toggle."""
    view = _make_diff_view()
    state = AppState()
    state._selected_diff_path = view.file_path

    @ui.page("/test_diff_toggle")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_toggle")
    await user.should_see("Unified")
    await user.should_see("Side by Side")


@pytest.mark.asyncio
async def test_render_diff_review_modal_close_button(user: User) -> None:
    """Verify Diff Review modal has a close button."""
    view = _make_diff_view()
    state = AppState()
    state._selected_diff_path = view.file_path

    @ui.page("/test_diff_close")
    def page() -> None:
        render_diff_modal(state, view)

    await user.open("/test_diff_close")
    await user.should_see("src/main.py")
