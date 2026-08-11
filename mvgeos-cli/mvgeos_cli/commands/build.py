from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from coding_mvge.mvge import CodingMvge
from mvgeos_agent.config_manager import ConfigManager
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.snapshot import RuntimeSnapshot
from rich.console import Console

console = Console()

build_app = typer.Typer(
    name="build",
    help="Serialise the resolved runtime manifest to JSON (read-only).",
)


async def _assemble(
    agent_name: str,
    extension_dir: str | None,
) -> RuntimeSnapshot:
    """Load runes and assemble the runtime snapshot (read-only).

    Creates a CodingMvge with a ConfigManager, loads runes and skills
    from disk, and returns a serialisable RuntimeSnapshot.  No API key
    or realm is required — this is a static introspection path.
    """
    config_manager = ConfigManager(agent_name=agent_name)
    agent = CodingMvge(
        api_key="",
        name=agent_name,
        extension_dir=extension_dir,
        config_manager=config_manager,
    )
    await agent._load_runes()
    return agent.build_snapshot()


@build_app.callback(invoke_without_command=True)
def build(
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name for agent-specific rune directory",
    ),
    extension_dir: str | None = typer.Option(
        None,
        "--extension-dir",
        "-e",
        help="Path to extension runes directory",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    ),
) -> None:
    """Serialise the resolved runtime manifest to JSON.

    Read-only: does not mutate config or state.  Outputs a JSON document
    describing spells (with source provenance), runes per scope, config
    values with provenance layers, resolved prompt source, loaded skills,
    and accumulated diagnostics.
    """
    snapshot = asyncio.run(_assemble(agent_name, extension_dir))
    json_str = snapshot.to_json()

    if output:
        out_path = Path(output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_str + "\n", encoding="utf-8")
        console.print(f"[green]Manifest written to {out_path}[/green]")
    else:
        console.print_json(json_str)
