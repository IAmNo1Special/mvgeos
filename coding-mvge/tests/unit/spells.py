from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)

import coding_mvge.spells as pkg_spells
from coding_mvge.spells import (
    edit,
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
