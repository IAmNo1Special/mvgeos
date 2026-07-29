import asyncio
import tempfile
from pathlib import Path

from mvgeos_spells.editing import cast_edit
from mvgeos_spells.types import SpellStatus


def test_cast_edit_exact_match() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        result = asyncio.run(cast_edit(str(path), "world", "universe"))
        assert result.status == SpellStatus.SUCCESS
        assert path.read_text(encoding="utf-8") == "hello universe"


def test_cast_edit_no_match() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        result = asyncio.run(cast_edit(str(path), "xyz", "abc"))
        assert result.status == SpellStatus.ERROR
        assert "Old string not found" in result.error_message


def test_cast_edit_multiple_occurrences() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world world", encoding="utf-8")
        result = asyncio.run(cast_edit(str(path), "world", "universe"))
        assert result.status == SpellStatus.SUCCESS
        assert path.read_text(encoding="utf-8") == "hello universe universe"


def test_cast_edit_nonexistent_file() -> None:
    result = asyncio.run(cast_edit("/nonexistent.txt", "a", "b"))
    assert result.status == SpellStatus.ERROR
    assert "File not found" in result.error_message
