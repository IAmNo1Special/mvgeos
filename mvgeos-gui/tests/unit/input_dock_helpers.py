from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.autocomplete import CommandKind, MentionChip, MentionKind
from mvgeos_gui.components.input_dock import (
    _autocomplete_icon,
    _autocomplete_icon_color,
    _chip_icon_color_for_kind,
    _chip_icon_for_kind,
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


def test_autocomplete_icon_variants() -> None:
    assert _autocomplete_icon(MentionKind.FILE) == "insert_drive_file"
    assert _autocomplete_icon(MentionKind.SKILL) == "auto_awesome"
    assert _autocomplete_icon(CommandKind.SLASH) == "slash"
    assert _autocomplete_icon(CommandKind.RUNE) == "auto_awesome"
    assert _autocomplete_icon("unknown") == "help_outline"


def test_autocomplete_icon_color_variants() -> None:
    assert _autocomplete_icon_color(MentionKind.FILE) == "text-[#8b949e]"
    assert _autocomplete_icon_color(MentionKind.SKILL) == "text-[#3b82f6]"
    assert _autocomplete_icon_color(CommandKind.RUNE) == "text-[#3b82f6]"
    assert _autocomplete_icon_color("unknown") == "text-[#8b949e]"


def test_chip_icon_for_kind() -> None:
    chip_file = MentionChip(text="@file", kind=MentionKind.FILE, path=Path("a.py"))
    assert _chip_icon_for_kind(MentionKind.FILE, chip_file) == "code"
    chip_skill = MentionChip(text="@skill", kind=MentionKind.SKILL, path=None)
    assert _chip_icon_for_kind(MentionKind.SKILL, chip_skill) == "auto_awesome"
    chip_slash = MentionChip(text="/cmd", kind=CommandKind.SLASH, path=None)
    assert _chip_icon_for_kind(CommandKind.SLASH, chip_slash) == "slash"


def test_chip_icon_color_for_kind() -> None:
    assert _chip_icon_color_for_kind(MentionKind.FILE) == "text-[#8b949e]"
    assert _chip_icon_color_for_kind(MentionKind.SKILL) == "text-[#3b82f6]"
    assert _chip_icon_color_for_kind("unknown") == "text-[#8b949e]"
