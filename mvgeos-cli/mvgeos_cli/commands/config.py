from __future__ import annotations

import json

import typer
from mvgeos_agent.config_manager import ConfigManager
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from rich.console import Console

console = Console()

config_app = typer.Typer(name="config", help="Configuration management")


def _get_manager(agent_name: str) -> ConfigManager:
    """Create a ConfigManager for the given agent name."""
    return ConfigManager(agent_name=agent_name)


@config_app.command("show")
def config_show(
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name (defaults to the canonical agent)",
    ),
) -> None:
    """Display current configuration with provenance."""
    mgr = _get_manager(agent_name)
    merged = mgr.load()
    output = {
        key: {"value": val.value, "layer": val.layer.value}
        for key, val in merged.items()
    }
    console.print_json(json.dumps(output, indent=2, default=str))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key to set"),
    value: str = typer.Argument(..., help="Value to set"),
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name (defaults to the canonical agent)",
    ),
) -> None:
    """Set a configuration value in the agent-scope file."""
    mgr = _get_manager(agent_name)

    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    mgr.set(key, parsed_value)
    console.print(f"[green]Set {key} = {parsed_value}[/green]")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Config key to get"),
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name (defaults to the canonical agent)",
    ),
) -> None:
    """Get a configuration value with provenance."""
    mgr = _get_manager(agent_name)
    val = mgr.get(key)
    output = json.dumps({"value": val.value, "layer": val.layer.value}, default=str)
    console.print(output)


@config_app.command("reset")
def config_reset(
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name (defaults to the canonical agent)",
    ),
) -> None:
    """Reset agent-scope configuration to defaults."""
    mgr = _get_manager(agent_name)
    mgr.reset()
    console.print("[green]Configuration reset to defaults[/green]")


@config_app.command("path")
def config_path(
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name (defaults to the canonical agent)",
    ),
) -> None:
    """Show the agent-scope config file path."""
    mgr = _get_manager(agent_name)
    console.print(str(mgr.agent_config_path))
