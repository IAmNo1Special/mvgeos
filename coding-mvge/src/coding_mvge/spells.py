"""Built-in coding spells and execution engine for CodingMvge."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from mvgeos_agent.spell_schema import generate_spell_schema
from mvgeos_agent.types import MvgeSpell, SpellResult, SpellStatus
from mvgeos_provider.types import AbortError

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


async def cast_read(path: str) -> SpellResult:
    """Read the contents of a file at the specified path."""
    try:
        file_path = Path(path)
        if not await asyncio.to_thread(file_path.exists):
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"File not found: {path}",
            )
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        return SpellResult(
            spell_name="read",
            status=SpellStatus.SUCCESS,
            content=content,
        )
    except Exception as exc:
        return SpellResult(
            spell_name="read",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def cast_write(path: str, content: str) -> SpellResult:
    """Write full content to a file at the specified path."""
    try:
        file_path = Path(path)
        await asyncio.to_thread(_write_file, file_path, content)
        return SpellResult(
            spell_name="write",
            status=SpellStatus.SUCCESS,
            content=f"Wrote to {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="write",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )


class _EditTargetNotFoundError(Exception):
    pass


def _edit_file(path: Path, old_string: str, new_string: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    content = path.read_text(encoding="utf-8")
    if old_string not in content:
        raise _EditTargetNotFoundError(old_string)
    path.write_text(content.replace(old_string, new_string), encoding="utf-8")


async def cast_edit(path: str, old_string: str, new_string: str) -> SpellResult:
    """Replace an exact string in a file with new content."""
    try:
        file_path = Path(path)
        await asyncio.to_thread(_edit_file, file_path, old_string, new_string)
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.SUCCESS,
            content=f"Updated {path}",
        )
    except _EditTargetNotFoundError:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=f"Old string not found in {path}",
        )
    except FileNotFoundError:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=f"File not found: {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )


async def cast_find(pattern: str, path: str = ".") -> SpellResult:
    """Find files matching a glob pattern relative to a directory path."""
    try:
        base = Path(path)
        if not await asyncio.to_thread(base.exists):
            return SpellResult(
                spell_name="find",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        matches = await asyncio.to_thread(lambda: list(base.rglob(pattern)))
        return SpellResult(
            spell_name="find",
            status=SpellStatus.SUCCESS,
            content="\n".join(str(m) for m in matches),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="find",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )


def _list_paths(base: Path, recursive: bool) -> list[str]:
    if not base.exists():
        raise FileNotFoundError(base)
    if recursive:
        items = sorted(str(p) for p in base.rglob("*") if p.is_file() or p.is_dir())
    else:
        items = sorted(str(p) for p in base.iterdir())
    return items


async def cast_list(path: str = ".", recursive: bool = False) -> SpellResult:
    """List directory contents, optionally recursively."""
    try:
        base = Path(path)
        items = await asyncio.to_thread(_list_paths, base, recursive)
        return SpellResult(
            spell_name="list",
            status=SpellStatus.SUCCESS,
            content="\n".join(items),
        )
    except FileNotFoundError:
        return SpellResult(
            spell_name="list",
            status=SpellStatus.ERROR,
            error_message=f"Path not found: {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="list",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )


async def cast_grep(
    pattern: str, path: str, output_mode: str = "content"
) -> SpellResult:
    """Search for a regex pattern in a file."""
    try:
        file_path = Path(path)
        exists = await asyncio.to_thread(file_path.exists)
        if not exists:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        is_file = await asyncio.to_thread(file_path.is_file)
        if not is_file:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.SUCCESS,
                content="",
            )
        text = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        regex = re.compile(pattern)
        matches: list[str] = []
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append(f"{i}: {line}" if output_mode == "content" else str(i))
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.SUCCESS,
            content="\n".join(matches),
        )
    except re.error as exc:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )


BUILTIN_SPELL_MAP: dict[str, Callable[..., Any]] = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}

DEFAULT_SPELL_MAP = BUILTIN_SPELL_MAP
DEFAULT_SPELL_NAMES = list(BUILTIN_SPELL_MAP.keys())


class _BuiltinSpell(MvgeSpell):
    """Bound executable MvgeSpell wrapping a built-in spell function."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
        )
        self._handler = handler

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> str:
        if signal is not None and getattr(signal, "aborted", False):
            raise AbortError("Operation aborted")
        validated = self.prepare_arguments(params)
        args = {k: v for k, v in validated.items() if v is not None}
        result: SpellResult = await self._handler(**args)
        if result.error_message:
            return f"[error] {result.error_message}"
        return result.content or f"{self.name} completed"


def create_builtin_spells(
    spell_names: Sequence[str] | None = None,
    workspace_root: Path | None = None,
    timeout_ms: int | None = None,
) -> list[MvgeSpell]:
    """Create bound MvgeSpell instances for requested built-in spell names."""
    names = list(spell_names) if spell_names is not None else DEFAULT_SPELL_NAMES
    spells: list[MvgeSpell] = []

    for name in names:
        if name not in BUILTIN_SPELL_MAP:
            continue
        func = BUILTIN_SPELL_MAP[name]
        doc = getattr(func, "__doc__", "")
        desc = doc.split("\n\n")[0].strip() if doc else f"Run the {name} tool."
        schema = generate_spell_schema(func)

        if name == "bash":
            # Pre-bind workspace root and default timeout
            async def _bound_bash(
                command: str,
                cwd: str | None = None,
                timeout_ms: int | None = None,
                _ws_root: Path | None = workspace_root,
                _default_timeout: int | None = timeout_ms,
            ) -> SpellResult:
                eff_timeout = timeout_ms if timeout_ms is not None else _default_timeout
                return await cast_bash(
                    command=command,
                    cwd=cwd,
                    timeout_ms=eff_timeout,
                    workspace_root=_ws_root,
                )

            spells.append(
                _BuiltinSpell(
                    name=name,
                    description=desc,
                    parameters=schema,
                    handler=_bound_bash,
                )
            )
        else:
            spells.append(
                _BuiltinSpell(
                    name=name,
                    description=desc,
                    parameters=schema,
                    handler=func,
                )
            )

    return spells
