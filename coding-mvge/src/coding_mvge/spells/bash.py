from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO

from mvgeos_agent.truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    MAX_BASH_BYTES,
    TruncationResult,
    format_size,
    truncation_details,
)
from mvgeos_agent.types import SpellResult, SpellStatus

from coding_mvge.spells._process_tree import (
    kill_process_tree,
    resolve_timeout_ms,
    resolve_workspace_root,
    validate_working_directory,
)

_BASH_READ_CHUNK = 65536
_RETAIN_TAIL_BYTES = 2 * DEFAULT_MAX_BYTES


class _CapExceededError(Exception):
    """Raised when combined stdout+stderr output passes the kill cap."""


class _TailAccumulator:
    """Retain the end of one stream with exact totals (bounded memory)."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.total_bytes = 0
        self.newlines = 0
        self.last_byte = b""
        self.starts_mid_line = False

    def feed(self, chunk: bytes) -> None:
        """Append a chunk, retaining only the tail."""
        if not chunk:
            return
        self.total_bytes += len(chunk)
        self.newlines += chunk.count(b"\n")
        self.last_byte = chunk[-1:]
        self.data += chunk
        overflow = len(self.data) - _RETAIN_TAIL_BYTES
        if overflow > 0:
            dropped = bytes(self.data[:overflow])
            del self.data[:overflow]
            self.starts_mid_line = not dropped.endswith(b"\n")

    def display(self) -> TruncationResult:
        """Bounded tail view with exact totals over the whole stream."""
        raw = bytes(self.data)
        if self.starts_mid_line:
            newline = raw.find(b"\n")
            if newline == -1:
                raw = _utf8_safe_suffix(raw, DEFAULT_MAX_BYTES)
            else:
                raw = raw[newline + 1 :]
        if len(raw) > DEFAULT_MAX_BYTES:
            raw = raw[-DEFAULT_MAX_BYTES:]
            newline = raw.find(b"\n")
            if newline == -1:
                raw = _utf8_safe_suffix(raw, DEFAULT_MAX_BYTES)
            else:
                raw = raw[newline + 1 :]
        split = raw.split(b"\n")
        if len(split) > DEFAULT_MAX_LINES:
            split = split[-DEFAULT_MAX_LINES:]
        text = b"\n".join(split).decode("utf-8", errors="replace")
        total_lines = self.newlines + (
            0 if self.total_bytes == 0 or self.last_byte == b"\n" else 1
        )
        shown = text.count("\n") + (1 if text else 0)
        truncated = self.total_bytes > len(raw) or total_lines > shown
        return TruncationResult(
            text=text,
            truncated=truncated,
            strategy="tail" if truncated else None,
            total_lines=total_lines,
            shown_start=(total_lines - shown + 1) if truncated and shown else None,
            shown_end=total_lines if truncated and shown else None,
            total_bytes=self.total_bytes,
        )


def _utf8_safe_suffix(data: bytes, limit: int) -> bytes:
    suffix = data[-limit:] if len(data) > limit else data
    for offset in range(min(4, len(suffix))):
        try:
            suffix[offset:].decode("utf-8")
            return suffix[offset:]
        except UnicodeDecodeError:
            continue
    return b""


def _spill_path() -> str:
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - handle outlives call; closed in finally
        prefix="mvgeos-bash-",
        suffix=".log",
        dir=tempfile.gettempdir(),
        delete=False,
    )
    handle.close()
    return handle.name


async def bash(
    command: str,
    cwd: str | None = None,
    timeout_ms: int | None = None,
    workspace_root: str | Path | None = None,
) -> SpellResult:
    """Execute a shell command with working directory confinement and timeout.

    Stdout keeps its tail (last 2000 lines / 50.0KB); truncated output
    spills the full stream to a temp file named in the result. Combined
    stdout+stderr beyond 50MB kills the process (first-hit wins with the
    timeout). Manual cleanup of spill files is the caller's duty.

    On Windows, commands run via PowerShell.
    On Unix/macOS, commands run via default shell.
    """
    try:
        resolved_root = resolve_workspace_root(workspace_root)
        target_cwd = validate_working_directory(cwd, resolved_root)
        effective_timeout_ms = resolve_timeout_ms(timeout_ms)
    except ValueError as exc:
        return SpellResult(
            spell_name="bash",
            status=SpellStatus.ERROR,
            content="",
            error_message=str(exc),
        )

    proc: asyncio.subprocess.Process | None = None
    spill: BinaryIO | None = None
    spill_path: str | None = None
    try:
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_cwd),
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_cwd),
                start_new_session=True,
            )
        stdout_acc = _TailAccumulator()
        stderr_acc = _TailAccumulator()
        assert proc is not None
        combined = bytearray()
        combined_total = 0

        def _ingest(acc: _TailAccumulator, chunk: bytes) -> None:
            nonlocal spill, spill_path, combined_total, combined
            combined_total += len(chunk)
            if combined_total > MAX_BASH_BYTES:
                raise _CapExceededError
            if spill is None and combined_total > DEFAULT_MAX_BYTES:
                spill_path = _spill_path()
                spill = open(spill_path, "wb")  # noqa: SIM115 - closed in finally
                spill.write(combined)
                combined = bytearray()
            if spill is not None:
                spill.write(chunk)
            else:
                combined += chunk
            acc.feed(chunk)

        async def _drain(
            stream: asyncio.StreamReader | None, acc: _TailAccumulator
        ) -> None:
            if stream is None:
                return
            while True:
                chunk = await stream.read(_BASH_READ_CHUNK)
                if not chunk:
                    return
                _ingest(acc, chunk)

        async def _run() -> int | None:
            await asyncio.gather(
                _drain(proc.stdout, stdout_acc),
                _drain(proc.stderr, stderr_acc),
            )
            await proc.wait()
            return proc.returncode

        try:
            returncode = await asyncio.wait_for(
                _run(), timeout=effective_timeout_ms / 1000
            )
        except TimeoutError:
            if proc is not None:
                await kill_process_tree(proc)
            return _partial_result(
                stdout_acc,
                spill_path,
                f"Command timed out after {effective_timeout_ms}ms",
            )
        except _CapExceededError:
            if proc is not None:
                await kill_process_tree(proc)
            return _partial_result(
                stdout_acc,
                spill_path,
                "Output exceeded 50MB cap; process killed",
            )
        stdout_view = stdout_acc.display()
        stderr_view = stderr_acc.display()
        if returncode != 0 and returncode is not None:
            stderr_text = stderr_view.text
            if stderr_view.truncated:
                stderr_text += "\n[stderr truncated]"
            return SpellResult(
                spell_name="bash",
                status=SpellStatus.ERROR,
                content=_render_stdout(stdout_view, spill_path),
                details=truncation_details(stdout_view, spill_path),
                error_message=stderr_text.strip(),
            )
        return SpellResult(
            spell_name="bash",
            status=SpellStatus.SUCCESS,
            content=_render_stdout(stdout_view, spill_path),
            details=truncation_details(stdout_view, spill_path),
        )
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
        if proc is not None:
            await kill_process_tree(proc)
        raise
    except Exception as exc:
        return SpellResult(
            spell_name="bash",
            status=SpellStatus.ERROR,
            content="",
            error_message=str(exc),
        )
    finally:
        if spill is not None:
            spill.close()


def _render_stdout(view: TruncationResult, spill_path: str | None) -> str:
    if not view.truncated or view.shown_start is None or view.shown_end is None:
        return view.text
    notice = (
        f"[Showing lines {view.shown_start}-{view.shown_end} "
        f"of {view.total_lines} ({format_size(DEFAULT_MAX_BYTES)} limit)."
    )
    if spill_path is not None:
        notice += f" Full output: {spill_path}]"
    else:
        notice += "]"
    return f"{view.text}\n\n{notice}" if view.text else notice


def _partial_result(
    stdout_acc: _TailAccumulator,
    spill_path: str | None,
    message: str,
) -> SpellResult:
    view = stdout_acc.display()
    content = _render_stdout(view, spill_path)
    content = f"{content}\n\n{message}" if content else message
    return SpellResult(
        spell_name="bash",
        status=SpellStatus.PARTIAL,
        content=content,
        details=truncation_details(view, spill_path),
        error_message=message,
    )
