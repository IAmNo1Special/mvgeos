import asyncio
import tempfile
from pathlib import Path

from mvgeos_spells.finding import cast_find
from mvgeos_spells.types import SpellStatus


def test_cast_find_pattern_match() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "file1.txt").write_text("content", encoding="utf-8")
        Path(tmpdir, "file2.py").write_text("content", encoding="utf-8")
        Path(tmpdir, "other.log").write_text("content", encoding="utf-8")
        result = asyncio.run(cast_find("*.txt", tmpdir))
        assert result.status == SpellStatus.SUCCESS
        assert "file1.txt" in result.content
        assert "file2.py" not in result.content


def test_cast_find_no_match() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "file1.txt").write_text("content", encoding="utf-8")
        result = asyncio.run(cast_find("*.py", tmpdir))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == ""


def test_cast_find_recursive() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "file.txt").write_text("content", encoding="utf-8")
        Path(tmpdir, "subdir").mkdir()
        Path(tmpdir, "subdir", "deep.txt").write_text("content", encoding="utf-8")
        result = asyncio.run(cast_find("*.txt", tmpdir))
        assert result.status == SpellStatus.SUCCESS
        assert "file.txt" in result.content
        assert "deep.txt" in result.content


def test_cast_find_nonexistent_path() -> None:
    result = asyncio.run(cast_find("*.txt", "/nonexistent/path"))
    assert result.status == SpellStatus.ERROR
    assert "Path not found" in result.error_message
