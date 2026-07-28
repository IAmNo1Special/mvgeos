import asyncio
import tempfile
from pathlib import Path

from mvgeos_spells.listing import cast_list
from mvgeos_spells.types import SpellStatus


def test_cast_list_non_recursive() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "file1.txt").write_text("content", encoding="utf-8")
        Path(tmpdir, "file2.py").write_text("content", encoding="utf-8")
        Path(tmpdir, "subdir").mkdir()
        result = asyncio.run(cast_list(tmpdir, recursive=False))
        assert result.status == SpellStatus.SUCCESS
        assert "file1.txt" in result.content
        assert "file2.py" in result.content
        assert "subdir" in result.content


def test_cast_list_recursive() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "file1.txt").write_text("content", encoding="utf-8")
        Path(tmpdir, "subdir").mkdir()
        Path(tmpdir, "subdir", "deep.txt").write_text("content", encoding="utf-8")
        result = asyncio.run(cast_list(tmpdir, recursive=True))
        assert result.status == SpellStatus.SUCCESS
        assert "file1.txt" in result.content
        assert "subdir" in result.content
        assert "deep.txt" in result.content


def test_cast_list_nonexistent_path() -> None:
    result = asyncio.run(cast_list("/nonexistent/path"))
    assert result.status == SpellStatus.ERROR
    assert "Path not found" in result.error_message
