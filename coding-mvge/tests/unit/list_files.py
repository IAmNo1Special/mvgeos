from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_agent.types import SpellStatus

from coding_mvge.spells import list_files


class TestListSpell:
    @pytest.mark.asyncio
    async def test_list_success(self, tmp_path: Path) -> None:
        (tmp_path / "file1.txt").touch()
        (tmp_path / "dir1").mkdir()

        result = await list_files(str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "file1.txt" in result.content
        assert "dir1/" in result.content

    @pytest.mark.asyncio
    async def test_list_sorted_case_insensitive(self, tmp_path: Path) -> None:
        (tmp_path / "b.txt").touch()
        (tmp_path / "C.txt").touch()
        (tmp_path / "a.txt").touch()

        result = await list_files(str(tmp_path))
        lines = result.content.splitlines()
        assert [Path(line).name for line in lines] == ["a.txt", "b.txt", "C.txt"]

    @pytest.mark.asyncio
    async def test_list_empty_directory(self, tmp_path: Path) -> None:
        result = await list_files(str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "(empty directory)"

    @pytest.mark.asyncio
    async def test_list_includes_dotfiles(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").touch()

        result = await list_files(str(tmp_path))
        assert ".hidden" in result.content

    @pytest.mark.asyncio
    async def test_list_explicit_ignored_path_honored(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "big.txt").touch()

        result = await list_files(str(venv))
        assert result.status == SpellStatus.SUCCESS
        assert "big.txt" in result.content

    @pytest.mark.asyncio
    async def test_list_limit_reached(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"f{i:02d}.txt").touch()

        result = await list_files(str(tmp_path), limit=3)
        assert result.status == SpellStatus.SUCCESS
        shown = [
            line
            for line in result.content.splitlines()
            if line and not line.startswith("[")
        ]
        assert len(shown) == 3
        assert shown[0].endswith("f00.txt")
        assert "3 entries limit reached" in result.content
        assert "limit=6" in result.content

    @pytest.mark.asyncio
    async def test_list_invalid_limit(self, tmp_path: Path) -> None:
        result = await list_files(str(tmp_path), limit=0)
        assert result.status == SpellStatus.ERROR
        assert "Invalid limit" in result.error_message

    @pytest.mark.asyncio
    async def test_list_limit_capped(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").touch()

        result = await list_files(str(tmp_path), limit=5000)
        assert result.status == SpellStatus.SUCCESS
        assert "Limit capped at 2000" in result.content

    @pytest.mark.asyncio
    async def test_list_byte_limit_notice(self, tmp_path: Path) -> None:
        for i in range(300):
            (tmp_path / f"{'n' * 100}{i:03d}.txt").touch()

        result = await list_files(str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "50.0KB limit reached" in result.content

    @pytest.mark.asyncio
    async def test_list_unreadable_entry_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").touch()
        with patch.object(Path, "is_dir", side_effect=[True, OSError("denied")]):
            result = await list_files(str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "(empty directory)"

    @pytest.mark.asyncio
    async def test_list_details_contract(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").touch()

        result = await list_files(str(tmp_path))
        assert result.details["truncation"]["version"] == 1
        assert result.details["truncation"]["backstop_applied"] is False
        assert result.details["truncation"]["full_output_path"] is None

    @pytest.mark.asyncio
    async def test_list_not_found(self, tmp_path: Path) -> None:
        result = await list_files(str(tmp_path / "missing"))
        assert result.status == SpellStatus.ERROR
        assert "Path not found" in result.error_message

    @pytest.mark.asyncio
    async def test_list_not_a_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.touch()

        result = await list_files(str(target))
        assert result.status == SpellStatus.ERROR
        assert "Not a directory" in result.error_message

    @pytest.mark.asyncio
    async def test_list_exception(self) -> None:
        with patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = await list_files("any")
            assert result.status == SpellStatus.ERROR
            assert "denied" in result.error_message
