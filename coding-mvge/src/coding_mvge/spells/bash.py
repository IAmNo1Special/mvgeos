from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus

DEFAULT_BASH_TIMEOUT_MS = 30000


def resolve_workspace_root(workspace_root: str | Path | None = None) -> Path:
    """Resolve the authorized workspace root."""
    if workspace_root is not None:
        return Path(workspace_root).resolve()
    env_root = os.environ.get("MVGEOS_WORKSPACE_ROOT") or os.environ.get(
        "MVGEOS_PROJECT_DIR"
    )
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd().resolve()


def validate_working_directory(cwd: str | Path | None, workspace_root: Path) -> Path:
    """Validate and constrain working directory to the authorized workspace root.

    Raises ValueError if cwd traverses outside workspace root or is invalid.
    """
    resolved_root = workspace_root.resolve()
    if cwd is None or str(cwd).strip() in ("", "."):
        target = resolved_root
    else:
        target_path = Path(cwd)
        if not target_path.is_absolute():
            target = (resolved_root / target_path).resolve()
        else:
            target = target_path.resolve()

    try:
        target.relative_to(resolved_root)
    except ValueError:
        raise ValueError(
            f"Working directory '{cwd}' is outside authorized workspace root "
            f"'{resolved_root}'."
        ) from None

    if not target.exists():
        raise ValueError(f"Working directory does not exist: '{target}'.")

    if not target.is_dir():
        raise ValueError(f"Working directory is not a directory: '{target}'.")

    return target


def resolve_timeout_ms(timeout_ms: int | None = None) -> int:
    """Resolve command timeout duration in milliseconds."""
    if timeout_ms is not None:
        if timeout_ms <= 0:
            raise ValueError("Timeout must be a positive integer in milliseconds.")
        return timeout_ms

    env_val = os.environ.get("MVGEOS_BASH_TIMEOUT_MS") or os.environ.get(
        "MVGEOS_SPELL_TIMEOUT_MS"
    )
    if env_val:
        try:
            val = int(env_val)
            if val > 0:
                return val
        except ValueError:
            pass

    return DEFAULT_BASH_TIMEOUT_MS


async def kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Cleanly terminate child process trees upon timeout or termination."""
    if proc.returncode is not None:
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            with contextlib.suppress(Exception):
                transport.close()
        return

    try:
        if sys.platform == "win32":
            kill_proc = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kill_proc.wait()
            kill_transport = getattr(kill_proc, "_transport", None)
            if kill_transport is not None:
                with contextlib.suppress(Exception):
                    kill_transport.close()
        else:
            try:
                sig = getattr(signal, "SIGKILL", signal.SIGTERM)
                os.killpg(os.getpgid(proc.pid), sig)
            except ProcessLookupError:
                pass
            except AttributeError:
                proc.kill()
    except Exception:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    with contextlib.suppress(Exception):
        await proc.wait()

    proc_transport = getattr(proc, "_transport", None)
    if proc_transport is not None:
        with contextlib.suppress(Exception):
            proc_transport.close()


async def cast_bash(
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
