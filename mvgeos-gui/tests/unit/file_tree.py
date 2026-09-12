"""Unit tests for the File Tree component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.file_tree import render_file_tree
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_file_tree_nonexistent(user: User) -> None:
    state = AppState(project_path=Path("/nonexistent/path/12345"))

    @ui.page("/test_file_tree_nonexistent")
    def page() -> None:
        render_file_tree(state)

    await user.open("/test_file_tree_nonexistent")
    await user.should_see("Project folder not found")


@pytest.mark.asyncio
async def test_file_tree_renders_files_and_dirs(tmp_path: Path, user: User) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested")
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / ".hidden").write_text("secret")

    state = AppState(project_path=tmp_path)
    state.open_in_editor = MagicMock()  # type: ignore[method-assign]

    @ui.page("/test_file_tree_valid")
    def page() -> None:
        render_file_tree(state)

    await user.open("/test_file_tree_valid")
    await user.should_see("file1.txt")
    await user.should_see("subdir")


@pytest.mark.asyncio
async def test_file_tree_permission_error(tmp_path: Path, user: User) -> None:
    state = AppState(project_path=tmp_path)

    with patch("pathlib.Path.iterdir", side_effect=PermissionError("denied")):

        @ui.page("/test_file_tree_perm_error")
        def page() -> None:
            render_file_tree(state)

        await user.open("/test_file_tree_perm_error")
