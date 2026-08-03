from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()

config_app = typer.Typer(name="config", help="Configuration management")

CONFIG_DIR = Path(".agents/.mvgeos")
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "model": "openrouter/free",
    "mana_budget": 10000,
    "max_tokens": 4096,
    "temperature": 0.7,
    "contemplation_level": "medium",
    "spells_enabled": ["bash", "read", "write", "edit", "find", "list", "grep"],
    "runes_paths": [".agents/.mvgeos/extensions"],
}


def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        data: dict[str, Any] = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data
    return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


@config_app.command("show")
def config_show() -> None:
    """Display current configuration."""
    config = load_config()
    console.print_json(json.dumps(config, indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key to set"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    """Set a configuration value."""
    config = load_config()

    # Try to parse as JSON first, then fallback to string
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    config[key] = parsed_value
    save_config(config)
    console.print(f"[green]Set {key} = {parsed_value}[/green]")


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="Config key to get")) -> None:
    """Get a configuration value."""
    config = load_config()
    if key in config:
        console.print(config[key])
    else:
        console.print(f"[red]Key not found: {key}[/red]")
        raise typer.Exit(1)


@config_app.command("reset")
def config_reset() -> None:
    """Reset configuration to defaults."""
    save_config(DEFAULT_CONFIG.copy())
    console.print("[green]Configuration reset to defaults[/green]")


@config_app.command("path")
def config_path() -> None:
    """Show the config file path."""
    console.print(str(CONFIG_FILE.resolve()))
