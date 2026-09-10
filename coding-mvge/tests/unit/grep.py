from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_agent.types import SpellStatus

from coding_mvge.spells import grep


class TestGrepSpell:
    @pytest.mark.asyncio
    async def test_grep_file_success(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("hello world\nline two", encoding="utf-8")

        result = await grep("hello", str(file1))
        assert result.status == SpellStatus.SUCCESS
        assert result.content.splitlines()[0].endswith("a.txt:1: hello world")

    @pytest.mark.asyncio
    async def test_grep_directory_tree(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("needle here", encoding="utf-8")
        (tmp_path / "a.txt").write_text("nothing", encoding="utf-8")

        result = await grep("needle", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "b.txt:1: needle here" in result.content

    @pytest.mark.asyncio
    async def test_grep_sorted_order(self, tmp_path: Path) -> None:
        (tmp_path / "z.txt").write_text("hit", encoding="utf-8")
        (tmp_path / "a.txt").write_text("hit", encoding="utf-8")

        result = await grep("hit", str(tmp_path))
        lines = [line for line in result.content.splitlines() if line]
        assert lines[0].endswith("a.txt:1: hit")
        assert lines[1].endswith("z.txt:1: hit")

    @pytest.mark.asyncio
    async def test_grep_prunes_ignored_by_default(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "h.py").write_text("needle", encoding="utf-8")
        (tmp_path / "v.py").write_text("needle", encoding="utf-8")

        result = await grep("needle", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "v.py" in result.content
        assert "h.py" not in result.content
        assert "include_ignored=True" in result.content

    @pytest.mark.asyncio
    async def test_grep_include_ignored_opt_in(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "h.py").write_text("needle", encoding="utf-8")

        result = await grep("needle", str(tmp_path), include_ignored=True)
        assert "h.py" in result.content

    @pytest.mark.asyncio
    async def test_grep_explicit_ignored_file_honored(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        target = venv / "h.py"
        target.write_text("needle", encoding="utf-8")

        result = await grep("needle", str(target))
        assert "needle" in result.content

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("nothing here", encoding="utf-8")
        result = await grep("zzz", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "No matches found" in result.content

    @pytest.mark.asyncio
    async def test_grep_limit_reached(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("\n".join(f"hit {i}" for i in range(10)), encoding="utf-8")

        result = await grep("hit", str(file1), limit=3)
        assert result.status == SpellStatus.SUCCESS
        assert "3 matches limit reached" in result.content
        assert "limit=6" in result.content

    @pytest.mark.asyncio
    async def test_grep_invalid_limit(self, tmp_path: Path) -> None:
        result = await grep("hit", str(tmp_path), limit=0)
        assert result.status == SpellStatus.ERROR
        assert "Invalid limit" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_invalid_context(self, tmp_path: Path) -> None:
        result = await grep("hit", str(tmp_path), context=-1)
        assert result.status == SpellStatus.ERROR
        assert "Invalid context" in result.error_message

    @pytest.mark.asyncio
    async def test_grep_skips_binary_and_undecodable(self, tmp_path: Path) -> None:
        (tmp_path / "good.txt").write_text("needle here", encoding="utf-8")
        (tmp_path / "blob.bin").write_bytes(b"\x00needle\xff")
        (tmp_path / "weird.txt").write_bytes(b"\xff\xfeneedle")

        result = await grep("needle", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "good.txt" in result.content
        assert "blob.bin" not in result.content
        assert "weird.txt" not in result.content

    @pytest.mark.asyncio
    async def test_grep_byte_budget_notice(self, tmp_path: Path) -> None:
        file1 = tmp_path / "big.txt"
        file1.write_text(
            "\n".join(f"hit {i:05d} " + "x" * 50 for i in range(3000)),
            encoding="utf-8",
        )

        result = await grep("hit", str(file1), limit=5000)
        assert result.status == SpellStatus.SUCCESS
        assert "50.0KB limit reached" in result.content
        assert result.details["truncation"]["truncated"] is True

    @pytest.mark.asyncio
    async def test_grep_glob_value_error_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("needle", encoding="utf-8")
        with patch.object(Path, "match", side_effect=ValueError("bad")):
            result = await grep("needle", str(tmp_path), glob="*.txt")
        assert result.status == SpellStatus.SUCCESS
        assert "No matches found" in result.content

    @pytest.mark.asyncio
    async def test_grep_unreadable_file_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("needle", encoding="utf-8")
        with patch.object(Path, "read_bytes", side_effect=OSError("denied")):
            result = await grep("needle", str(tmp_path))
        assert result.status == SpellStatus.SUCCESS
        assert "No matches found" in result.content

    @pytest.mark.asyncio
    async def test_grep_context_overlap_merged(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("one\ntwo\nthree\nfour", encoding="utf-8")

        result = await grep("two|three", str(file1), context=1)
        assert result.status == SpellStatus.SUCCESS
        lines = result.content.splitlines()
        assert len(lines) == 4
        assert lines[0].endswith("-1- one")
        assert lines[1].endswith(":2: two")

    @pytest.mark.asyncio
    async def test_grep_context_lines(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("before\nneedle\ntrail", encoding="utf-8")

        result = await grep("needle", str(file1), context=1)
        assert result.status == SpellStatus.SUCCESS
        assert ":2: needle" in result.content
        assert "-1- before" in result.content
        assert "-3- trail" in result.content

    @pytest.mark.asyncio
    async def test_grep_literal(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("axb\na.b", encoding="utf-8")

        result = await grep("a.b", str(file1), literal=True)
        assert ":2: a.b" in result.content
        assert ":1:" not in result.content.split("[")[0]

    @pytest.mark.asyncio
    async def test_grep_ignore_case(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("HELLO", encoding="utf-8")

        result = await grep("hello", str(file1), ignore_case=True)
        assert "HELLO" in result.content

    @pytest.mark.asyncio
    async def test_grep_glob_filter(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("needle", encoding="utf-8")
        (tmp_path / "b.txt").write_text("needle", encoding="utf-8")

        result = await grep("needle", str(tmp_path), glob="*.py")
        assert "a.py" in result.content
        assert "b.txt" not in result.content.split("[")[0]

    @pytest.mark.asyncio
    async def test_grep_long_line_keeps_match(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.txt"
        file1.write_text("x" * 2000 + "needle", encoding="utf-8")

        result = await grep("needle", str(file1))
        assert result.status == SpellStatus.SUCCESS
        assert "needle" in result.content
        assert "..." in result.content
        assert "truncated to 500 chars" in result.content

    @pytest.mark.asyncio
    async def test_grep_details_contract(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        result = await grep("hello", str(tmp_path))
        assert result.details["truncation"]["version"] == 1
        assert result.details["truncation"]["backstop_applied"] is False

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
