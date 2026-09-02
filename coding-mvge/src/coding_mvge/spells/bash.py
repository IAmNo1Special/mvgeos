from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus

from coding_mvge.spells._process_tree import (
    kill_process_tree,
    resolve_timeout_ms,
    resolve_workspace_root,
    validate_working_directory,
)


async def bash(
    command: str,
    cwd: str | None = None,
    timeout_ms: int | None = None,
    workspace_root: str | Path | None = None,
) -> SpellResult:
    """Execute a shell command with working directory confinement and timeout.

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
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout_ms / 1000
            )
        except TimeoutError:
            await kill_process_tree(proc)
            return SpellResult(
                spell_name="bash",
                status=SpellStatus.PARTIAL,
                content="",
                error_message=f"Command timed out after {effective_timeout_ms}ms",
            )
        except BaseException:
            await kill_process_tree(proc)
            raise

        if proc.returncode != 0:
            return SpellResult(
                spell_name="bash",
                status=SpellStatus.ERROR,
                content=stdout.decode("utf-8", errors="replace"),
                error_message=stderr.decode("utf-8", errors="replace").strip(),
            )

        return SpellResult(
            spell_name="bash",
            status=SpellStatus.SUCCESS,
            content=stdout.decode("utf-8", errors="replace"),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="bash",
            status=SpellStatus.ERROR,
            content="",
            error_message=str(exc),
        )
