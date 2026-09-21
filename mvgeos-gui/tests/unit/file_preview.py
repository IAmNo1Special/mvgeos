"""Unit tests for the file preview dialog (Major #6).

Clicking a file in the workspace tree must open an in-browser read-only
preview. The old behavior spawned a server-side ``$EDITOR`` binary, which
is a dead control for every web-GUI user.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.file_preview import render_file_preview_dialog
from mvgeos_gui.state import AppState


def test_open_file_preview_sets_path_and_notifies(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    state = AppState(project_path=tmp_path)
    assert state.preview_file is None
    state.open_file_preview(target)
    assert state.preview_file == target


def test_close_file_preview_clears_path(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    state = AppState(project_path=tmp_path)
    state.open_file_preview(target)
    state.close_file_preview()
    assert state.preview_file is None


@pytest.mark.asyncio
async def test_preview_dialog_renders_file_content(tmp_path: Path, user: User) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("hello preview\nsecond line\n")
    state = AppState(project_path=tmp_path)
    state.open_file_preview(target)

    @ui.page("/test_file_preview")
    def page() -> None:
        render_file_preview_dialog(state)

    await user.open("/test_file_preview")
    await user.should_see("notes.txt")
    await user.should_see("hello preview")


@pytest.mark.asyncio
async def test_preview_dialog_renders_nothing_when_closed(
    tmp_path: Path, user: User
) -> None:
    state = AppState(project_path=tmp_path)

    @ui.page("/test_file_preview_closed")
    def page() -> None:
        render_file_preview_dialog(state)

    await user.open("/test_file_preview_closed")
    await user.should_not_see("File preview")


@pytest.mark.asyncio
async def test_preview_dialog_handles_binary_file(tmp_path: Path, user: User) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"\x00\x01\x02binary\xff")
    state = AppState(project_path=tmp_path)
    state.open_file_preview(target)

    @ui.page("/test_file_preview_binary")
    def page() -> None:
        render_file_preview_dialog(state)

    await user.open("/test_file_preview_binary")
    await user.should_see("cannot be previewed")


@pytest.mark.asyncio
async def test_preview_dialog_handles_missing_file(tmp_path: Path, user: User) -> None:
    state = AppState(project_path=tmp_path)
    state.open_file_preview(tmp_path / "gone.txt")

    @ui.page("/test_file_preview_missing")
    def page() -> None:
        render_file_preview_dialog(state)

    await user.open("/test_file_preview_missing")
    await user.should_see("could not be read")
