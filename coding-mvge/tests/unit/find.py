from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_agent.types import SpellStatus

from coding_mvge.spells import find


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
    async def test_find_sorted_posix_order(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.py").touch()
        (tmp_path / "z.py").touch()
        (tmp_path / "a.py").touch()

        result = await find("*.py", str(tmp_path))
        lines = [
            line
            for line in result.content.splitlines()
            if line and not line.startswith("[")
        ]
        assert lines == sorted(lines)
        assert lines[0].endswith("a.py")

    @pytest.mark.asyncio
    async def test_find_prunes_ignored_by_default(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "hidden.py").touch()
        (tmp_path / "visible.py").touch()

        result = await find("*.py", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "visible.py" in result.content
        assert "hidden.py" not in result.content
        assert "include_ignored=True" in result.content

    @pytest.mark.asyncio
    async def test_find_include_ignored_opt_in(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "hidden.py").touch()

        result = await find("*.py", str(tmp_path), include_ignored=True)
        assert result.status == SpellStatus.SUCCESS
        assert "hidden.py" in result.content

    @pytest.mark.asyncio
    async def test_find_explicit_ignored_base_honored(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "hidden.py").touch()

        result = await find("*.py", str(venv))
        assert result.status == SpellStatus.SUCCESS
        assert "hidden.py" in result.content

    @pytest.mark.asyncio
    async def test_find_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").touch()

        result = await find("*.py", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "No files found matching pattern" in result.content

    @pytest.mark.asyncio
    async def test_find_limit_reached(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"f{i:02d}.py").touch()

        result = await find("*.py", str(tmp_path), limit=3)
        assert result.status == SpellStatus.SUCCESS
        assert "3 results limit reached" in result.content
        assert "limit=6" in result.content

    @pytest.mark.asyncio
    async def test_find_invalid_limit(self, tmp_path: Path) -> None:
        result = await find("*.py", str(tmp_path), limit=0)
        assert result.status == SpellStatus.ERROR
        assert "Invalid limit" in result.error_message

    @pytest.mark.asyncio
    async def test_find_limit_capped(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").touch()

        result = await find("*.py", str(tmp_path), limit=5000)
        assert result.status == SpellStatus.SUCCESS
        assert "Limit capped at 2000" in result.content

    @pytest.mark.asyncio
    async def test_find_byte_limit_notice(self, tmp_path: Path) -> None:
        for i in range(300):
            (tmp_path / f"{'n' * 100}{i:03d}.py").touch()

        result = await find("*.py", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "50.0KB limit reached" in result.content

    @pytest.mark.asyncio
    async def test_find_pattern_value_error_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").touch()
        with patch.object(Path, "match", side_effect=ValueError("bad")):
            result = await find("*.py", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "No files found matching pattern" in result.content

    @pytest.mark.asyncio
    async def test_find_details_contract(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").touch()

        result = await find("*.py", str(tmp_path))
        assert result.details["truncation"]["version"] == 1
        assert result.details["truncation"]["backstop_applied"] is False

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
