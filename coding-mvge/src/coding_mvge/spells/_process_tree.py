from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

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
    """Validate and constrain working directory to the authorized workspace root."""
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
