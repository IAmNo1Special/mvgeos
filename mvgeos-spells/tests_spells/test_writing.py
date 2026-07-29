import asyncio
import tempfile
from pathlib import Path

from mvgeos_spells.types import SpellStatus
from mvgeos_spells.writing import cast_write


def test_cast_write_new_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "new_file.txt"
        result = asyncio.run(cast_write(str(path), "hello world"))
        assert result.status == SpellStatus.SUCCESS
        assert path.read_text(encoding="utf-8") == "hello world"


def test_cast_write_overwrite_existing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "existing.txt"
        path.write_text("old content", encoding="utf-8")
        result = asyncio.run(cast_write(str(path), "new content"))
        assert result.status == SpellStatus.SUCCESS
        assert path.read_text(encoding="utf-8") == "new content"


def test_cast_write_creates_parent_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "nested" / "deep" / "file.txt"
        result = asyncio.run(cast_write(str(path), "deep content"))
        assert result.status == SpellStatus.SUCCESS
        assert path.read_text(encoding="utf-8") == "deep content"
