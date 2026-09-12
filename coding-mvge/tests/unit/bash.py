from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_agent.function_spell import FunctionSpell
from mvgeos_core.spells import SpellStatus

from coding_mvge.spells._process_tree import (
    DEFAULT_BASH_TIMEOUT_MS,
    kill_process_tree,
    resolve_timeout_ms,
    resolve_workspace_root,
    validate_working_directory,
)
from coding_mvge.spells.bash import bash


class _FakeReader:
    """Async stream reader yielding fixed chunks then EOF."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, _n: int) -> bytes:
        await asyncio.sleep(0)
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _EndlessReader:
    """Reader that never EOFs, for output-cap tests."""

    async def read(self, n: int) -> bytes:
        await asyncio.sleep(0)
        return b"x" * n


def _mock_proc(
    stdout_chunks: list[bytes] | None = None,
    stderr_chunks: list[bytes] | None = None,
    returncode: int = 0,
) -> MagicMock:
    proc = MagicMock()
    proc.stdout = (
        _FakeReader(stdout_chunks) if stdout_chunks is not None else _FakeReader([])
    )
    proc.stderr = (
        _FakeReader(stderr_chunks) if stderr_chunks is not None else _FakeReader([])
    )
    proc.wait = AsyncMock(return_value=returncode)
    proc.returncode = returncode
    proc.pid = 9999
    return proc


def _patch_spawn(proc: MagicMock) -> Any:
    return (
        patch("asyncio.create_subprocess_shell", new=AsyncMock(return_value=proc)),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    )


class TestTimeoutResolution:
    def test_explicit_timeout(self) -> None:
        assert resolve_timeout_ms(5000) == 5000

    def test_invalid_explicit_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            resolve_timeout_ms(0)
        with pytest.raises(ValueError, match="positive integer"):
            resolve_timeout_ms(-100)

    def test_env_var_bash_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MVGEOS_BASH_TIMEOUT_MS", "12345")
        assert resolve_timeout_ms() == 12345

    def test_env_var_spell_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MVGEOS_BASH_TIMEOUT_MS", raising=False)
        monkeypatch.setenv("MVGEOS_SPELL_TIMEOUT_MS", "67890")
        assert resolve_timeout_ms() == 67890

    def test_invalid_env_var_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MVGEOS_BASH_TIMEOUT_MS", "invalid_num")
        assert resolve_timeout_ms() == DEFAULT_BASH_TIMEOUT_MS

    def test_default_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MVGEOS_BASH_TIMEOUT_MS", raising=False)
        monkeypatch.delenv("MVGEOS_SPELL_TIMEOUT_MS", raising=False)
        assert resolve_timeout_ms() == DEFAULT_BASH_TIMEOUT_MS


class TestWorkspaceResolutionAndValidation:
    def test_resolve_workspace_root_explicit(self, tmp_path: Path) -> None:
        assert resolve_workspace_root(str(tmp_path)) == tmp_path.resolve()
        assert resolve_workspace_root(tmp_path) == tmp_path.resolve()

    def test_resolve_workspace_root_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MVGEOS_WORKSPACE_ROOT", str(tmp_path))
        assert resolve_workspace_root() == tmp_path.resolve()

    def test_resolve_workspace_root_project_dir_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MVGEOS_WORKSPACE_ROOT", raising=False)
        monkeypatch.setenv("MVGEOS_PROJECT_DIR", str(tmp_path))
        assert resolve_workspace_root() == tmp_path.resolve()

    def test_resolve_workspace_root_fallback_cwd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MVGEOS_WORKSPACE_ROOT", raising=False)
        monkeypatch.delenv("MVGEOS_PROJECT_DIR", raising=False)
        assert resolve_workspace_root() == Path.cwd().resolve()

    def test_validate_working_dir_none_or_empty(self, tmp_path: Path) -> None:
        root = tmp_path.resolve()
        assert validate_working_directory(None, root) == root
        assert validate_working_directory("", root) == root
        assert validate_working_directory(".", root) == root

    def test_validate_working_dir_subfolder(self, tmp_path: Path) -> None:
        root = tmp_path.resolve()
        sub = root / "src"
        sub.mkdir()
        assert validate_working_directory("src", root) == sub
        assert validate_working_directory(str(sub), root) == sub

    def test_validate_working_dir_outside_bounds_raises(self, tmp_path: Path) -> None:
        root = tmp_path / "workspace"
        root.mkdir()
        outside = tmp_path / "other"
        outside.mkdir()

        with pytest.raises(ValueError, match="outside authorized workspace root"):
            validate_working_directory(str(outside), root.resolve())

        with pytest.raises(ValueError, match="outside authorized workspace root"):
            validate_working_directory("../other", root.resolve())

    def test_validate_working_dir_not_found(self, tmp_path: Path) -> None:
        root = tmp_path.resolve()
        with pytest.raises(ValueError, match="does not exist"):
            validate_working_directory("nonexistent", root)

    def test_validate_working_dir_not_a_directory(self, tmp_path: Path) -> None:
        root = tmp_path.resolve()
        file_path = root / "file.txt"
        file_path.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            validate_working_directory("file.txt", root)


class TestKillProcessTree:
    @pytest.mark.asyncio
    async def test_kill_process_tree_already_exited(self) -> None:
        proc = MagicMock()
        proc.returncode = 0
        await kill_process_tree(proc)
        proc.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_kill_process_tree_windows(self) -> None:
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 1234
        proc.wait = AsyncMock()

        kill_subproc = MagicMock()
        kill_subproc.wait = AsyncMock()

        with (
            patch("coding_mvge.spells._process_tree.sys.platform", "win32"),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=kill_subproc),
            ) as mock_exec,
        ):
            await kill_process_tree(proc)
            mock_exec.assert_called_once_with(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                "1234",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            kill_subproc.wait.assert_awaited_once()
            proc.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kill_process_tree_posix(self) -> None:
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 1234
        proc.wait = AsyncMock()

        with (
            patch("coding_mvge.spells._process_tree.sys.platform", "linux"),
            patch(
                "coding_mvge.spells._process_tree.os.getpgid",
                create=True,
                return_value=1234,
            ) as mock_getpgid,
            patch(
                "coding_mvge.spells._process_tree.os.killpg", create=True
            ) as mock_killpg,
        ):
            await kill_process_tree(proc)
            mock_getpgid.assert_called_once_with(1234)
            mock_killpg.assert_called_once()
            proc.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kill_process_tree_fallback_on_error(self) -> None:
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 1234
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        with (
            patch("coding_mvge.spells._process_tree.sys.platform", "win32"),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=RuntimeError("taskkill error"),
            ),
        ):
            await kill_process_tree(proc)
            proc.kill.assert_called_once()
            proc.wait.assert_awaited_once()


class TestCastBash:
    @pytest.mark.asyncio
    async def test_cast_bash_success(self, tmp_path: Path) -> None:
        result = await bash(
            command="echo hello_bash",
            workspace_root=tmp_path,
        )
        assert result.status == SpellStatus.SUCCESS
        assert "hello_bash" in result.content

    @pytest.mark.asyncio
    async def test_cast_bash_with_valid_cwd(self, tmp_path: Path) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "marker.txt").write_text("found_marker", encoding="utf-8")

        result = await bash(
            command="dir" if os.name == "nt" else "ls",
            cwd="subdir",
            workspace_root=tmp_path,
        )
        assert result.status == SpellStatus.SUCCESS
        assert "marker.txt" in result.content

    @pytest.mark.asyncio
    async def test_cast_bash_cwd_violation_returns_error(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()

        result = await bash(
            command="echo hi",
            cwd="../outside",
            workspace_root=workspace,
        )
        assert result.status == SpellStatus.ERROR
        assert "outside authorized workspace root" in result.error_message

    @pytest.mark.asyncio
    async def test_cast_bash_cwd_not_found_returns_error(self, tmp_path: Path) -> None:
        result = await bash(
            command="echo hi",
            cwd="does_not_exist",
            workspace_root=tmp_path,
        )
        assert result.status == SpellStatus.ERROR
        assert "does not exist" in result.error_message

    @pytest.mark.asyncio
    async def test_cast_bash_timeout(self, tmp_path: Path) -> None:
        mock_proc = _mock_proc()
        mock_proc.stdout.read = AsyncMock(side_effect=TimeoutError())

        shell_patch, exec_patch = _patch_spawn(mock_proc)
        with (
            shell_patch,
            exec_patch,
            patch(
                "coding_mvge.spells.bash.kill_process_tree", new=AsyncMock()
            ) as mock_kill,
        ):
            result = await bash(
                command="sleep 100",
                timeout_ms=50,
                workspace_root=tmp_path,
            )
            assert result.status == SpellStatus.PARTIAL
            assert "Command timed out after 50ms" in result.error_message
            mock_kill.assert_awaited_once_with(mock_proc)

    @pytest.mark.asyncio
    async def test_cast_bash_nonzero_exit(self, tmp_path: Path) -> None:
        result = await bash(
            command="exit 1" if os.name != "nt" else "cmd /c exit 1",
            workspace_root=tmp_path,
        )
        assert result.status == SpellStatus.ERROR

    @pytest.mark.asyncio
    async def test_cast_bash_cancelled(self, tmp_path: Path) -> None:
        mock_proc = _mock_proc()
        mock_proc.stdout.read = AsyncMock(side_effect=asyncio.CancelledError())

        shell_patch, exec_patch = _patch_spawn(mock_proc)
        with (
            shell_patch,
            exec_patch,
            patch(
                "coding_mvge.spells.bash.kill_process_tree", new=AsyncMock()
            ) as mock_kill,
            pytest.raises(asyncio.CancelledError),
        ):
            await bash(
                command="sleep 100",
                timeout_ms=10_000,
                workspace_root=tmp_path,
            )
        mock_kill.assert_awaited_once_with(mock_proc)

    @pytest.mark.asyncio
    async def test_cast_bash_generic_exception(self, tmp_path: Path) -> None:
        with (
            patch(
                "asyncio.create_subprocess_shell",
                side_effect=OSError("spawn failed"),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("spawn failed"),
            ),
        ):
            result = await bash(
                command="echo hi",
                workspace_root=tmp_path,
            )
            assert result.status == SpellStatus.ERROR
            assert "spawn failed" in result.error_message


class TestBuiltinSpellBash:
    @pytest.mark.asyncio
    async def test_builtin_spell_enforces_workspace_root(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        spell = FunctionSpell(bash)
        result = await spell.execute(
            "call-1",
            {
                "command": "echo hi",
                "cwd": "../outside",
                "workspace_root": str(workspace),
            },
        )
        assert result.status == SpellStatus.ERROR
        assert "outside authorized workspace root" in result.error_message

    @pytest.mark.asyncio
    async def test_builtin_spell_execution(self, tmp_path: Path) -> None:
        async def mock_bash(
            command: str,
            cwd: str | None = None,
            timeout_ms: int | None = None,
            workspace_root: str | Path | None = None,
        ) -> Any:
            return "done"

        spell = FunctionSpell(mock_bash, name="bash")
        assert spell.name == "bash"
        result = await spell.execute(
            "call-1", {"command": "echo hi", "timeout_ms": 12345}
        )
        assert result == "done"


class TestBashBounding:
    @pytest.mark.asyncio
    async def test_small_output_no_spill(self, tmp_path: Path) -> None:
        proc = _mock_proc([b"hello\nworld\n"])
        shell_patch, exec_patch = _patch_spawn(proc)
        with shell_patch, exec_patch:
            result = await bash(command="echo hi", workspace_root=tmp_path)
        assert result.status == SpellStatus.SUCCESS
        assert result.content == "hello\nworld\n"
        assert result.details["truncation"]["truncated"] is False
        assert result.details["truncation"]["full_output_path"] is None
        assert result.details["truncation"]["version"] == 1

    @pytest.mark.asyncio
    async def test_large_output_tail_truncation_with_spill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        lines = [f"line{i:05d}\n".encode() for i in range(10000)]
        proc = _mock_proc(lines)
        shell_patch, exec_patch = _patch_spawn(proc)
        with shell_patch, exec_patch:
            result = await bash(command="seq", workspace_root=tmp_path)
        assert result.status == SpellStatus.SUCCESS
        assert result.details["truncation"]["truncated"] is True
        assert result.details["truncation"]["strategy"] == "tail"
        assert "line09999" in result.content
        assert "line00000" not in result.content
        assert "Full output:" in result.content
        spill = Path(result.details["truncation"]["full_output_path"])
        assert spill.is_file()
        assert b"line00000" in spill.read_bytes()
        assert b"line09999" in spill.read_bytes()

    @pytest.mark.asyncio
    async def test_output_cap_kills_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys.modules["coding_mvge.spells.bash"], "MAX_BASH_BYTES", 1024
        )
        proc = MagicMock()
        proc.stdout = _EndlessReader()
        proc.stderr = _FakeReader([])
        proc.wait = AsyncMock(return_value=0)
        proc.returncode = 0
        proc.pid = 9999

        shell_patch, exec_patch = _patch_spawn(proc)
        with (
            shell_patch,
            exec_patch,
            patch(
                "coding_mvge.spells.bash.kill_process_tree", new=AsyncMock()
            ) as mock_kill,
        ):
            result = await bash(command="yes", workspace_root=tmp_path)
        assert result.status == SpellStatus.PARTIAL
        assert "process killed" in result.error_message
        mock_kill.assert_awaited_once_with(proc)

    @pytest.mark.asyncio
    async def test_none_stream_is_skipped(self, tmp_path: Path) -> None:
        proc = _mock_proc([b"out\n"])
        proc.stdout = None
        shell_patch, exec_patch = _patch_spawn(proc)
        with shell_patch, exec_patch:
            result = await bash(command="echo hi", workspace_root=tmp_path)
        assert result.status == SpellStatus.SUCCESS
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_stderr_truncation_marked(self, tmp_path: Path) -> None:
        err = [f"err{i:05d}-{'y' * 30}\n".encode() for i in range(3000)]
        proc = _mock_proc([], err, returncode=1)
        shell_patch, exec_patch = _patch_spawn(proc)
        with shell_patch, exec_patch:
            result = await bash(command="nope", workspace_root=tmp_path)
        assert result.status == SpellStatus.ERROR
        assert "[stderr truncated]" in result.error_message

    @pytest.mark.asyncio
    async def test_lines_only_truncation_has_no_spill(self, tmp_path: Path) -> None:
        lines = [f"l{i:04d}\n".encode() for i in range(2500)]
        proc = _mock_proc(lines)
        shell_patch, exec_patch = _patch_spawn(proc)
        with shell_patch, exec_patch:
            result = await bash(command="seq", workspace_root=tmp_path)
        assert result.status == SpellStatus.SUCCESS
        assert result.details["truncation"]["truncated"] is True
        assert result.details["truncation"]["full_output_path"] is None
        assert "Full output" not in result.content


class TestTailAccumulator:
    def test_empty_feed(self) -> None:
        from coding_mvge.spells.bash import _TailAccumulator

        acc = _TailAccumulator()
        acc.feed(b"")
        view = acc.display()
        assert view.truncated is False
        assert view.text == ""
        assert view.total_lines == 0

    def test_overflow_trims_to_tail(self) -> None:
        from coding_mvge.spells.bash import _TailAccumulator

        acc = _TailAccumulator()
        acc.feed(b"A" * 110_000)
        acc.feed(b"\nend\n")
        view = acc.display()
        assert view.truncated is True
        assert view.strategy == "tail"
        assert view.text == "end\n"
        assert view.total_lines == 2
        assert view.shown_start == 1
        assert view.shown_end == 2

    def test_utf8_safe_suffix(self) -> None:
        from coding_mvge.spells.bash import _utf8_safe_suffix

        assert _utf8_safe_suffix(b"\xff\xffABC", 4) == b"ABC"
        assert _utf8_safe_suffix(b"hello", 10) == b"hello"
