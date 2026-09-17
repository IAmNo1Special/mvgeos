from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Annotated

import typer
from mvgeos_core.constants import DEFAULT_AGENT_NAME
from mvgeos_runes.loader import (
    get_prioritized_skill_search_paths,
    load_skill_manifest,
    load_skills_from_paths,
)
from mvgeos_runes.types import (
    SkillDiagnostic,
    SkillDiagnosticKind,
    SkillScope,
)
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
        else list(get_prioritized_skill_search_paths(agent_name))
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


@skill_app.command("list")
def skill_list(
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name for agent-specific skill directory",
    ),
    cwd: str | None = typer.Option(
        None,
        "--cwd",
        help="Custom project working directory to discover skills from",
    ),
) -> None:
    """List all available skills across project, user, agent, and plugin scopes."""
    effective_cwd = Path(cwd) if cwd else None
    paths = get_prioritized_skill_search_paths(agent_name=agent_name, cwd=effective_cwd)
    loads, diagnostics = load_skills_from_paths(paths, agent_name)

    if not loads:
        console.print("[yellow]No skills found.[/yellow]")
        return

    ascii_only = not is_utf8_stream(sys.stdout)
    box_style = box.ASCII if ascii_only else box.HEAVY_HEAD
    table = Table(title="Available Skills", box=box_style)
    table.add_column("Skill", style="cyan")
    table.add_column("Scope", style="green")
    table.add_column("Description", style="white")
    table.add_column("Path", style="yellow")

    for load in loads:
        m = load.manifest
        table.add_row(
            m.name,
            m.scope.value if m.scope else "unknown",
            clip_text(m.description, 60, ascii_only),
            clip_text(m.location or m.path, PATH_MAX_WIDTH, ascii_only),
        )

    console.print(table)


@skill_app.command("validate")
def skill_validate(
    target: Annotated[
        Path,
        typer.Argument(
            help="Path to a skill directory or SKILL.md file",
        ),
    ],
) -> None:
    """Validate a skill strictly against the agentskills.io specification."""
    resolved = target.resolve()
    if not resolved.exists():
        console.print(f"[red]FAIL: Path does not exist: {target}[/red]")
        raise typer.Exit(1)

    skill_md = (
        resolved
        if resolved.is_file() and resolved.name == "SKILL.md"
        else resolved / "SKILL.md"
    )
    if not skill_md.is_file():
        console.print(f"[red]FAIL: Missing SKILL.md in {resolved}[/red]")
        raise typer.Exit(1)

    skill_dir = skill_md.parent
    diagnostics: list[SkillDiagnostic] = []
    manifest = load_skill_manifest(
        skill_dir,
        diagnostics=diagnostics,
        lenient=False,
    )

    # Check path containment for files in skill directory
    for f in skill_dir.rglob("*"):
        try:
            if not str(f.resolve()).startswith(str(skill_dir.resolve())):
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.PATH_ESCAPE,
                        skill_name=skill_dir.name,
                        message=f"File '{f.name}' resolves outside skill directory",
                        path=str(f),
                    )
                )
        except OSError:
            pass

    # Check for relative path escapes in SKILL.md body
    if manifest and manifest.body:
        for match in re.finditer(r"(?:\.\./)+[a-zA-Z0-9_./-]+", manifest.body):
            escaped_ref = match.group(0)
            target_path = (skill_dir / escaped_ref).resolve()
            if not str(target_path).startswith(str(skill_dir.resolve())):
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.PATH_ESCAPE,
                        skill_name=skill_dir.name,
                        message=(
                            f"Reference '{escaped_ref}' in SKILL.md "
                            "escapes skill directory"
                        ),
                        path=str(skill_md),
                    )
                )

    errors = [
        d
        for d in diagnostics
        if d.kind
        in (
            SkillDiagnosticKind.PARSE_WARNING,
            SkillDiagnosticKind.MALFORMED_YAML,
            SkillDiagnosticKind.PATH_ESCAPE,
            SkillDiagnosticKind.INVALID_PLUGIN,
        )
    ]

    if manifest is None or errors:
        console.print(f"[red]FAIL: Validation failed for {skill_md.parent.name}:[/red]")
        for err in errors:
            console.print(f"  - ({err.kind.value}) {err.message}")
        raise typer.Exit(1)

    console.print(
        f"[green]OK: Skill '{manifest.name}' is a valid conformant "
        "agentskills.io skill.[/green]"
    )
    console.print(f"  Name: {manifest.name}")
    console.print(f"  Description: {manifest.description}")
    console.print(f"  Location: {manifest.location}")
    if manifest.version:
        console.print(f"  Version: {manifest.version}")
