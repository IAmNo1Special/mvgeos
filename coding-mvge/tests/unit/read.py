from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_core.spells import SpellStatus

from coding_mvge.spells import read


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

    @pytest.mark.asyncio
    async def test_read_offset_limit_window(self, tmp_path: Path) -> None:
        file = tmp_path / "lines.txt"
        file.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")
        result = await read(str(file), offset=3, limit=2)
        assert result.status == SpellStatus.SUCCESS
        assert "line3\nline4" in result.content
        assert "line5" not in result.content.split("[")[0]
        assert "more lines in file" in result.content
        assert "offset=5" in result.content

    @pytest.mark.asyncio
    async def test_read_user_limit_notice(self, tmp_path: Path) -> None:
        file = tmp_path / "lines.txt"
        file.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")
        result = await read(str(file), limit=4)
        assert result.status == SpellStatus.SUCCESS
        assert "more lines in file" in result.content
        assert "offset=5" in result.content

    @pytest.mark.asyncio
    async def test_read_offset_beyond_end(self, tmp_path: Path) -> None:
        file = tmp_path / "lines.txt"
        file.write_text("a\nb", encoding="utf-8")
        result = await read(str(file), offset=10)
        assert result.status == SpellStatus.ERROR
        assert "beyond end of file" in result.error_message

    @pytest.mark.asyncio
    async def test_read_invalid_offset_limit(self, tmp_path: Path) -> None:
        file = tmp_path / "lines.txt"
        file.write_text("a", encoding="utf-8")
        result = await read(str(file), offset=0)
        assert result.status == SpellStatus.ERROR
        assert "Invalid offset" in result.error_message
        result = await read(str(file), limit=0)
        assert result.status == SpellStatus.ERROR
        assert "Invalid limit" in result.error_message

    @pytest.mark.asyncio
    async def test_read_binary_file(self, tmp_path: Path) -> None:
        file = tmp_path / "blob.bin"
        file.write_bytes(b"\x00\x01\x02binary\xff\xfe")
        result = await read(str(file))
        assert result.status == SpellStatus.ERROR
        assert "Binary" in result.error_message

    @pytest.mark.asyncio
    async def test_read_undecodable_file(self, tmp_path: Path) -> None:
        file = tmp_path / "weird.bin"
        file.write_bytes(b"\xff\xfe\xfdabc")
        result = await read(str(file))
        assert result.status == SpellStatus.ERROR
        assert "Binary" in result.error_message

    @pytest.mark.asyncio
    async def test_read_trailing_newline_count(self, tmp_path: Path) -> None:
        file = tmp_path / "lines.txt"
        file.write_bytes(b"a\nb\n")
        result = await read(str(file))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "a\nb"
        beyond = await read(str(file), offset=3)
        assert beyond.status == SpellStatus.ERROR
        assert "(2 lines total)" in beyond.error_message

    @pytest.mark.asyncio
    async def test_read_directory_without_skill_md(self, tmp_path: Path) -> None:
        result = await read(str(tmp_path))
        assert result.status == SpellStatus.ERROR

    @pytest.mark.asyncio
    async def test_read_large_file_truncates_with_notice(self, tmp_path: Path) -> None:
        file = tmp_path / "big.txt"
        file.write_text(
            "\n".join(f"line{i:05d}" for i in range(20000)), encoding="utf-8"
        )
        result = await read(str(file))
        assert result.status == SpellStatus.SUCCESS
        assert "Use offset=" in result.content
        assert result.details["truncation"]["truncated"] is True
        assert result.details["truncation"]["version"] == 1

    @pytest.mark.asyncio
    async def test_read_first_line_exceeds_limit(self, tmp_path: Path) -> None:
        file = tmp_path / "wide.txt"
        file.write_text("y" * 60_000, encoding="utf-8")
        result = await read(str(file))
        assert result.status == SpellStatus.SUCCESS
        assert "exceeds" in result.content
        assert "sed" not in result.content

    @pytest.mark.asyncio
    async def test_read_offset_with_truncation(self, tmp_path: Path) -> None:
        file = tmp_path / "wide2.txt"
        file.write_text(
            "\n".join(f"line{i:05d}-{'x' * 30}" for i in range(3000)),
            encoding="utf-8",
        )
        result = await read(str(file), offset=1000)
        assert result.status == SpellStatus.SUCCESS
        assert "Showing lines 1000-" in result.content
        assert "Use offset=" in result.content
