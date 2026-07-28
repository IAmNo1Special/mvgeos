import asyncio
import tempfile
from pathlib import Path

from mvgeos_spells.reading import cast_read
from mvgeos_spells.types import SpellStatus


def test_cast_read_existing_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        result = asyncio.run(cast_read(str(path)))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "hello world"


def test_cast_read_nonexistent_file() -> None:
    result = asyncio.run(cast_read("/nonexistent/path.txt"))
    assert result.status == SpellStatus.ERROR
    assert "File not found" in result.error_message


def test_cast_read_encoding() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "utf8.txt"
        content = "hello \u00e9 world"
        path.write_text(content, encoding="utf-8")
        result = asyncio.run(cast_read(str(path)))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == content
