from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_agent.types import SpellStatus

from coding_mvge.spells.edit import cast_edit
from coding_mvge.spells.find import cast_find
from coding_mvge.spells.grep import cast_grep
from coding_mvge.spells.list import cast_list
from coding_mvge.spells.read import cast_read
from coding_mvge.spells.write import cast_write


class TestReadSpell:
    @pytest.mark.asyncio
    async def test_read_success(self, tmp_path: Path) -> None:
        file = tmp_path / "hello.txt"
        file.write_text("hello world", encoding="utf-8")
        result = await cast_read(str(file))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "hello world"

    @pytest.mark.asyncio
    async def test_read_not_found(self, tmp_path: Path) -> None:
        result = await cast_read(str(tmp_path / "missing.txt"))
        assert result.status == SpellStatus.ERROR
        assert "File not found" in result.error_message

    @pytest.mark.asyncio
    async def test_read_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await cast_read("any.txt")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestWriteSpell:
    @pytest.mark.asyncio
    async def test_write_success(self, tmp_path: Path) -> None:
        file = tmp_path / "out.txt"
        result = await cast_write(str(file), "new content")
        assert result.status == SpellStatus.SUCCESS
        assert file.read_text(encoding="utf-8") == "new content"

    @pytest.mark.asyncio
    async def test_write_exception(self) -> None:
        with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
            result = await cast_write("out.txt", "data")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestEditSpell:
    @pytest.mark.asyncio
    async def test_edit_success(self, tmp_path: Path) -> None:
        file = tmp_path / "doc.txt"
        file.write_text("foo bar baz", encoding="utf-8")
        result = await cast_edit(str(file), "bar", "qux")
        assert result.status == SpellStatus.SUCCESS
        assert file.read_text(encoding="utf-8") == "foo qux baz"

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, tmp_path: Path) -> None:
        result = await cast_edit(str(tmp_path / "nope.txt"), "a", "b")
        assert result.status == SpellStatus.ERROR
        assert "File not found" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_old_string_not_found(self, tmp_path: Path) -> None:
        file = tmp_path / "doc.txt"
        file.write_text("foo bar baz", encoding="utf-8")
        result = await cast_edit(str(file), "missing", "replacement")
        assert result.status == SpellStatus.ERROR
        assert "Old string not found" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await cast_edit("any.txt", "a", "b")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestFindSpell:
    @pytest.mark.asyncio
    async def test_find_success(self, tmp_path: Path) -> None:
        (tmp_path / "test1.py").touch()
        (tmp_path / "test2.py").touch()
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "test3.py").touch()

        result = await cast_find("*.py", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "test1.py" in result.content
        assert "test3.py" in result.content

    @pytest.mark.asyncio
    async def test_find_not_found(self, tmp_path: Path) -> None:
        result = await cast_find("*.py", str(tmp_path / "missing"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_find_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await cast_find("*.py", "any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestGrepSpell:
    @pytest.mark.asyncio
    async def test_grep_success(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("hello world\nline two", encoding="utf-8")

        result = await cast_grep("hello", str(file1))
        assert result.status == SpellStatus.SUCCESS
        assert "hello world" in result.content

        result_lines = await cast_grep("hello", str(file1), output_mode="lines")
        assert result_lines.status == SpellStatus.SUCCESS
        assert result_lines.content == "1"

    @pytest.mark.asyncio
    async def test_grep_not_found(self, tmp_path: Path) -> None:
        result = await cast_grep("hello", str(tmp_path / "missing.txt"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("hello", encoding="utf-8")
        result = await cast_grep("[invalid", str(file1))
        assert result.status == SpellStatus.ERROR
        assert "unterminated character set" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await cast_grep("hello", "any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestListSpell:
    @pytest.mark.asyncio
    async def test_list_success(self, tmp_path: Path) -> None:
        (tmp_path / "file1.txt").touch()
        (tmp_path / "dir1").mkdir()

        result = await cast_list(str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "file1.txt" in result.content
        assert "dir1" in result.content

    @pytest.mark.asyncio
    async def test_list_not_found(self, tmp_path: Path) -> None:
        result = await cast_list(str(tmp_path / "missing"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_list_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await cast_list("any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message
