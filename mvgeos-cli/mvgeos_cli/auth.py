from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import typer
from rich.console import Console

from mvgeos_cli.console import get_console

AUTH_FILE_PATH = Path("~/.agents/.mvgeos/auth/openrouter.json").expanduser()
AUTH_FILE_PERMS = 0o600
AUTH_DIR_PERMS = 0o700


def enforce_file_permissions(
    path: Path,
    mode: int = AUTH_FILE_PERMS,
    dir_mode: int = AUTH_DIR_PERMS,
) -> None:
    """Enforce restricted POSIX permissions on a file and its parent directory."""
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):
        if path.parent.exists():
            path.parent.chmod(dir_mode)
        if path.exists():
            path.chmod(mode)


def load_api_key_from_auth() -> str | None:
    """Load API key from ~/.agents/.mvgeos/auth/openrouter.json."""
    if AUTH_FILE_PATH.exists():
        if os.name != "nt":
            enforce_file_permissions(AUTH_FILE_PATH)
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
            api_key = data.get("api_key")
            return api_key if isinstance(api_key, str) and api_key.strip() else None
    return None


def save_api_key_to_auth(api_key: str) -> Path:
    """Save API key to ~/.agents/.mvgeos/auth/openrouter.json."""
    AUTH_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        with contextlib.suppress(OSError):
            AUTH_FILE_PATH.parent.chmod(AUTH_DIR_PERMS)

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(AUTH_FILE_PATH), flags, AUTH_FILE_PERMS)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as f:
            f.write(json.dumps({"api_key": api_key}, indent=2))
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise

    if os.name != "nt":
        with contextlib.suppress(OSError):
            AUTH_FILE_PATH.chmod(AUTH_FILE_PERMS)
    return AUTH_FILE_PATH


def prompt_api_key(console: Console | None = None) -> str | None:
    """Prompt user interactively for OpenRouter API key."""
    if console is None:
        console = get_console()
    try:
        entered = typer.prompt("Enter OpenRouter API key", hide_input=True)
        return entered.strip() if entered else None
    except KeyboardInterrupt, EOFError, typer.Abort:
        console.print("[red]Aborted.[/red]")
        return None
