from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import typer
from rich.console import Console

from mvgeos_cli.console import get_console

AUTH_FILE_PATH = Path("~/.agents/.mvgeos/auth/openrouter.json").expanduser()


def load_api_key_from_auth() -> str | None:
    """Load API key from ~/.agents/.mvgeos/auth/openrouter.json."""
    if AUTH_FILE_PATH.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(AUTH_FILE_PATH.read_text(encoding="utf-8"))
            api_key = data.get("api_key")
            return api_key if isinstance(api_key, str) and api_key.strip() else None
    return None


def save_api_key_to_auth(api_key: str) -> Path:
    """Save API key to ~/.agents/.mvgeos/auth/openrouter.json."""
    AUTH_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE_PATH.write_text(
        json.dumps({"api_key": api_key}, indent=2), encoding="utf-8"
    )
    if os.name != "nt":
        with contextlib.suppress(OSError):
            AUTH_FILE_PATH.chmod(0o600)
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
