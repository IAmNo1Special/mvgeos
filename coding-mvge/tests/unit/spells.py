from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_agent.types import SpellResult, SpellStatus

import coding_mvge.spells as pkg_spells
from coding_mvge.spells import (
    edit,
    find,
    grep,
    list_files,
    read,
    write,
)


class TestSpellsPackage:
    def test_spells_package_exports(self) -> None:
        import runpy

        res = runpy.run_path(str(Path(pkg_spells.__file__)))

        assert "read" in res["__all__"]
        assert "write" in res["__all__"]
        assert "edit" in res["__all__"]
        assert "find" in res["__all__"]
        assert "grep" in res["__all__"]
        assert "list_files" in res["__all__"]
        assert "bash" in res["__all__"]


class TestReadSpell:
    @pytest.mark.asyncio
    async def test_read_success(self, tmp_path: Path) -> None:
        file = tmp_path / "hello.txt"
        file.write_text("hello world", encoding="utf-8")
        result = await read(str(file))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "hello world"

    @pytest.mark.asyncio
    async def test_read_not_found(self, tmp_path: Path) -> None:
        result = await read(str(tmp_path / "missing.txt"))
        assert result.status == SpellStatus.ERROR
        assert "File not found" in result.error_message

    @pytest.mark.asyncio
    async def test_read_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await read("any.txt")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message

    @pytest.mark.asyncio
    async def test_read_directory_with_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Skill Content", encoding="utf-8")
        result = await read(str(skill_dir))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "# Skill Content"


class TestWriteSpell:
    @pytest.mark.asyncio
    async def test_write_success(self, tmp_path: Path) -> None:
        file = tmp_path / "out.txt"
        result = await write(str(file), "new content")
        assert result.status == SpellStatus.SUCCESS
        assert file.read_text(encoding="utf-8") == "new content"

    @pytest.mark.asyncio
    async def test_write_exception(self) -> None:
        with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
            result = await write("out.txt", "data")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestEditSpell:
    @pytest.mark.asyncio
    async def test_edit_success(self, tmp_path: Path) -> None:
        file = tmp_path / "doc.txt"
        file.write_text("foo bar baz", encoding="utf-8")
        result = await edit(str(file), "bar", "qux")
        assert result.status == SpellStatus.SUCCESS
        assert file.read_text(encoding="utf-8") == "foo qux baz"

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, tmp_path: Path) -> None:
        result = await edit(str(tmp_path / "nope.txt"), "a", "b")
        assert result.status == SpellStatus.ERROR
        assert "File not found" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_old_string_not_found(self, tmp_path: Path) -> None:
        file = tmp_path / "doc.txt"
        file.write_text("foo bar baz", encoding="utf-8")
        result = await edit(str(file), "missing", "replacement")
        assert result.status == SpellStatus.ERROR
        assert "Old string not found" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await edit("any.txt", "a", "b")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestFindSpell:
    @pytest.mark.asyncio
    async def test_find_success(self, tmp_path: Path) -> None:
        (tmp_path / "test1.py").touch()
        (tmp_path / "test2.py").touch()
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "test3.py").touch()

        result = await find("*.py", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "test1.py" in result.content
        assert "test3.py" in result.content

    @pytest.mark.asyncio
    async def test_find_not_found(self, tmp_path: Path) -> None:
        result = await find("*.py", str(tmp_path / "missing"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_find_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await find("*.py", "any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message


class TestGrepSpell:
    @pytest.mark.asyncio
    async def test_grep_success(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("hello world\nline two", encoding="utf-8")

        result = await grep("hello", str(file1))
        assert result.status == SpellStatus.SUCCESS
        assert "hello world" in result.content

        result_lines = await grep("hello", str(file1), output_mode="lines")
        assert result_lines.status == SpellStatus.SUCCESS
        assert result_lines.content == "1"

    @pytest.mark.asyncio
    async def test_grep_not_found(self, tmp_path: Path) -> None:
        result = await grep("hello", str(tmp_path / "missing.txt"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("hello", encoding="utf-8")
        result = await grep("[invalid", str(file1))
        assert result.status == SpellStatus.ERROR
        assert "unterminated character set" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await grep("hello", "any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_directory_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        result = await grep("hello", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == ""


class TestSpellConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes_no_race(self, tmp_path: Path) -> None:
        files = [(tmp_path / f"f{i}.txt") for i in range(20)]
        for f in files:
            f.write_text("seed", encoding="utf-8")

        async def roundtrip(f: Path) -> tuple[SpellResult, SpellResult, SpellResult]:
            r1 = await read(str(f))
            w1 = await write(str(f), "updated")
            r2 = await read(str(f))
            return r1, w1, r2

        results = await asyncio.gather(*(roundtrip(f) for f in files))
        for r1, w1, r2 in results:
            assert r1.status == SpellStatus.SUCCESS
            assert r1.content == "seed"
            assert w1.status == SpellStatus.SUCCESS
            assert r2.status == SpellStatus.SUCCESS
            assert r2.content == "updated"


class TestListSpell:
    @pytest.mark.asyncio
    async def test_list_success(self, tmp_path: Path) -> None:
        (tmp_path / "file1.txt").touch()
        (tmp_path / "dir1").mkdir()

        result = await list_files(str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "file1.txt" in result.content
        assert "dir1" in result.content

    @pytest.mark.asyncio
    async def test_list_not_found(self, tmp_path: Path) -> None:
        result = await list_files(str(tmp_path / "missing"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_list_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await list_files("any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message
