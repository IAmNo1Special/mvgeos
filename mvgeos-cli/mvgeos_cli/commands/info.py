from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import typer
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.snapshot import RuntimeSnapshot
from rich.console import Console
from rich.table import Table

from mvgeos_cli.commands.build import _assemble

console = Console()

info_app = typer.Typer(
    name="info",
    help="Display the runtime snapshot as rich tables (read-only).",
)


def _render_snapshot(snap: RuntimeSnapshot) -> str:
    """Render a RuntimeSnapshot as human-readable rich tables.

    Returns the rendered text so callers can assert on it in tests.
    """
    out = StringIO()
    console = Console(file=out, width=100, record=True, force_terminal=False)

    console.print(f"[bold]Agent:[/bold] {snap.agent_name}")
    console.print(f"[bold]Model:[/bold] {snap.model}")
    console.print()

    _render_spells(console, snap)
    _render_runes(console, snap)
    _render_config(console, snap)
    _render_prompt(console, snap)
    _render_guidelines(console, snap)
    _render_skills(console, snap)
    _render_diagnostics(console, snap)

    return out.getvalue()


def _render_spells(console: Console, snap: RuntimeSnapshot) -> None:
    table = Table(title="Spells", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Source Rune", style="yellow")
    table.add_column("Description")

    for spell in snap.spells:
        source_rune = spell.source_rune if spell.source_rune is not None else "-"
        table.add_row(
            spell.name,
            spell.source.value,
            source_rune,
            spell.description or "-",
        )

    if not snap.spells:
        table.add_row("[dim](none)", "", "", "")

    console.print(table)


def _render_runes(console: Console, snap: RuntimeSnapshot) -> None:
    table = Table(title="Runes", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="green")
    table.add_column("Version", style="yellow")
    table.add_column("Enabled", style="magenta")
    table.add_column("Path")
    table.add_column("Entry Point")
    table.add_column("Hooks")

    for rune in snap.runes:
        hooks = ", ".join(rune.hooks) if rune.hooks else "-"
        table.add_row(
            rune.name,
            rune.scope,
            rune.version,
            str(rune.enabled),
            rune.path,
            rune.entry_point or "-",
            hooks,
        )

    if not snap.runes:
        table.add_row("[dim](none)", "", "", "", "", "", "")

    console.print(table)


def _render_config(console: Console, snap: RuntimeSnapshot) -> None:
    table = Table(title="Config", show_lines=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Layer", style="yellow")
    table.add_column("Source File")

    for entry in snap.config:
        source_file = entry.source_file if entry.source_file is not None else "-"
        table.add_row(
            entry.key,
            str(entry.value),
            entry.layer,
            source_file,
        )

    if not snap.config:
        table.add_row("[dim](none)", "", "", "")

    console.print(table)


def _render_prompt(console: Console, snap: RuntimeSnapshot) -> None:
    if snap.prompt is None:
        return

    table = Table(title="Prompt", show_lines=False)
    table.add_column("Source", style="cyan")
    table.add_column("Path", style="yellow")
    table.add_column("Text")

    path = snap.prompt.path if snap.prompt.path is not None else "-"
    table.add_row(
        snap.prompt.source,
        path,
        snap.prompt.text or "-",
    )

    console.print(table)


def _render_guidelines(console: Console, snap: RuntimeSnapshot) -> None:
    if not snap.guidelines:
        return

    table = Table(title="Guidelines", show_lines=False)
    table.add_column("Index", style="cyan")
    table.add_column("Guideline")

    for i, g in enumerate(snap.guidelines):
        table.add_row(str(i), g)

    console.print(table)


def _render_skills(console: Console, snap: RuntimeSnapshot) -> None:
    table = Table(title="Skills", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="green")
    table.add_column("Path", style="yellow")
    table.add_column("Version")
    table.add_column("Description")

    for skill in snap.skills:
        table.add_row(
            skill.name,
            skill.scope,
            skill.path,
            skill.version or "-",
            skill.description or "-",
        )

    if not snap.skills:
        table.add_row("[dim](none)", "", "", "", "")

    console.print(table)


def _render_diagnostics(console: Console, snap: RuntimeSnapshot) -> None:
    table = Table(title="Diagnostics", show_lines=False)
    table.add_column("Kind", style="red")
    table.add_column("Target", style="yellow")
    table.add_column("Name", style="cyan")
    table.add_column("Scope")
    table.add_column("Path")
    table.add_column("Message")

    for diag in snap.diagnostics:
        scope = diag.scope if diag.scope is not None else "-"
        path = diag.path if diag.path else "-"
        table.add_row(
            diag.kind,
            diag.target,
            diag.name,
            scope,
            path,
            diag.message,
        )

    if not snap.diagnostics:
        table.add_row("[dim](none)", "", "", "", "", "")

    console.print(table)


@info_app.callback(invoke_without_command=True)
def info(
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
    """Display the runtime snapshot as rich tables.

    Read-only: does not mutate config or state.  Renders spells with
    source provenance, runes per scope with enabled state, config values
    with provenance layers, loaded skills with source, and diagnostics.
    """
    snapshot = asyncio.run(_assemble(agent_name, extension_dir))
    render_text = _render_snapshot(snapshot)

    if output:
        out_path = Path(output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_text + "\n", encoding="utf-8")
        console.print(f"[green]Snapshot written to {out_path}[/green]")
    else:
        console.print(render_text, end="")
