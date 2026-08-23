from pathlib import Path

from mvgeos_gui.components.input_dock import _get_file_icon, _truncate


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
