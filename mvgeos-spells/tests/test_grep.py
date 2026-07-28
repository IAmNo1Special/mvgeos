import asyncio
import tempfile
from pathlib import Path

from mvgeos_spells.grep import cast_grep
from mvgeos_spells.types import SpellStatus


def test_cast_grep_content_match() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world\nhello universe\nfoo bar", encoding="utf-8")
        result = asyncio.run(cast_grep("hello", str(path)))
        assert result.status == SpellStatus.SUCCESS
        assert "1: hello world" in result.content
        assert "2: hello universe" in result.content
        assert "foo bar" not in result.content


def test_cast_grep_line_numbers_only() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world\nhello universe", encoding="utf-8")
        result = asyncio.run(cast_grep("hello", str(path), output_mode="line"))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "1\n2"


def test_cast_grep_no_match() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        result = asyncio.run(cast_grep("xyz", str(path)))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == ""


def test_cast_grep_nonexistent_path() -> None:
    result = asyncio.run(cast_grep("pattern", "/nonexistent/path"))
    assert result.status == SpellStatus.ERROR
    assert "Path not found" in result.error_message
