from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import typer
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_runes.loader import (
    discover_plugin_skill_paths,
    get_default_skill_paths,
    load_skills_from_paths,
)
from mvgeos_runes.types import SkillDiagnosticKind, SkillScope
from rich import box
from rich.console import Console
from rich.table import Table

from mvgeos_cli.console import clip_text, format_error, get_console, is_utf8_stream

console = get_console()

skill_app = typer.Typer(
    name="skill",
    help="Inspect and clean up agent skills.",
)

PATH_MAX_WIDTH = 50


@dataclass
class ShadowedSkill:
    """A skill copy shadowed by a higher-precedence scope."""

    name: str
    shadow_scope: SkillScope
    shadow_dir: Path
    winner_scope: SkillScope
    winner_dir: Path


def plan_skill_dedupe(
    agent_name: str,
    skill_paths: list[tuple[str | Path, SkillScope]] | None = None,
) -> list[ShadowedSkill]:
    """Plan removal of skill copies shadowed by a higher-precedence scope.

    Uses the loader's own first-wins resolution, so only copies the loader
    would ignore are reported. Pure: never touches the filesystem.
    """
    paths = (
        list(skill_paths)
        if skill_paths is not None
        else [
            *get_default_skill_paths(agent_name),
            *discover_plugin_skill_paths(),
        ]
    )
    loads, diagnostics = load_skills_from_paths(paths, agent_name)
    winners = {load.manifest.name: load.manifest for load in loads}

    plan: list[ShadowedSkill] = []
    for diag in diagnostics:
        if diag.kind != SkillDiagnosticKind.SHADOWED_SKILL:
            continue
        if diag.scope is None:
            continue
        winner = winners.get(diag.skill_name)
        if winner is None:
            continue
        plan.append(
            ShadowedSkill(
                name=diag.skill_name,
                shadow_scope=diag.scope,
                shadow_dir=Path(diag.path) / diag.skill_name,
                winner_scope=winner.scope,
                winner_dir=Path(winner.path),
            )
        )
    return plan


def _render_dedupe_plan(plan: list[ShadowedSkill], ascii_only: bool = False) -> str:
    """Render the dedupe plan as a Rich table string (for testing/assertions)."""
    out = StringIO()
    box_style = box.ASCII if ascii_only else box.HEAVY_HEAD
    render_console = Console(file=out, width=200, record=True, force_terminal=False)
    table = Table(title="Shadowed Skills", box=box_style)
    table.add_column("Skill", style="cyan")
    table.add_column("Shadowed Scope", style="red")
    table.add_column("Shadowed Path", style="yellow", width=PATH_MAX_WIDTH)
    table.add_column("Winner Scope", style="green")
    table.add_column("Winner Path", width=PATH_MAX_WIDTH)

    for entry in plan:
        table.add_row(
            entry.name,
            entry.shadow_scope.value,
            clip_text(str(entry.shadow_dir), PATH_MAX_WIDTH - 2, ascii_only),
            entry.winner_scope.value,
            clip_text(str(entry.winner_dir), PATH_MAX_WIDTH - 2, ascii_only),
        )

    render_console.print(table)
    return out.getvalue()


@skill_app.callback(invoke_without_command=True)
def skill_callback(ctx: typer.Context) -> None:
    """Inspect and clean up agent skills."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@skill_app.command("dedupe")
def skill_dedupe(
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name for agent-specific skill directory",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="List shadowed skills without deleting anything",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Delete shadowed skill copies without prompting",
    ),
) -> None:
    """Remove skill copies shadowed by a higher-precedence scope.

    Scope order is project, then user, then agent: a skill installed in
    both user and agent scope loads from user scope, so the agent copy
    is dead weight. Without --yes nothing is deleted.
    """
    try:
        plan = plan_skill_dedupe(agent_name)
    except OSError as exc:
        console.print(format_error(exc))
        raise typer.Exit(1) from None

    if not plan:
        console.print("[green]No shadowed skills found.[/green]")
        return

    ascii_only = not is_utf8_stream(sys.stdout)
    console.print(_render_dedupe_plan(plan, ascii_only=ascii_only))

    if dry_run or not yes:
        console.print(
            f"[yellow]Re-run with --yes to remove "
            f"{len(plan)} shadowed skill directorie(s).[/yellow]"
        )
        return

    removed = 0
    for entry in plan:
        target = entry.shadow_dir
        if not target.is_dir() or target.name != entry.name:
            console.print(f"[yellow]Skipped non-directory: {target}[/yellow]")
            continue
        shutil.rmtree(target)
        removed += 1
    console.print(f"[green]Removed {removed} shadowed skill directorie(s).[/green]")
