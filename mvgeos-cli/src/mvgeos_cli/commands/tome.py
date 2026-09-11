from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import typer
from mvgeos_core.constants import DEFAULT_TOME_DIR
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntry, TomeMetadata
from rich import box
from rich.console import Console
from rich.table import Table

from mvgeos_cli.console import clip_text, format_error, get_console, is_utf8_stream

console = get_console()
tome_app = typer.Typer(name="tome", help="Session tome management")

CWD_MAX_WIDTH = 50


@tome_app.callback(invoke_without_command=True)
def tome_callback(ctx: typer.Context) -> None:
    """Session tome management."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


def get_tome_dir() -> Path:
    tome_dir = DEFAULT_TOME_DIR
    tome_dir.mkdir(parents=True, exist_ok=True)
    return tome_dir


@tome_app.command("list")
def tome_list() -> None:
    """List all tomes."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)
    ascii_only = not is_utf8_stream(sys.stdout)

    console.print(_render_tome_list(ledger.list_tomes(), ascii_only=ascii_only))


def _render_tome_list(metas: list[TomeMetadata], ascii_only: bool = False) -> str:
    """Render tome metadata as a Rich table string (for testing/assertions)."""
    out = StringIO()
    box_style = box.ASCII if ascii_only else box.HEAVY_HEAD
    render_console = Console(file=out, width=150, record=True, force_terminal=False)
    table = Table(title="MvgeOS Tomes", box=box_style)
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Created", style="green", width=21)
    table.add_column("CWD", style="yellow", width=CWD_MAX_WIDTH)
    table.add_column("Active Leaf", style="magenta", width=15)

    for meta in metas:
        table.add_row(
            meta.id[:8],
            meta.created_at[:19],
            clip_text(meta.cwd, CWD_MAX_WIDTH - 2, ascii_only),
            meta.active_leaf_id or "-",
        )

    render_console.print(table)
    return out.getvalue()


def _format_timestamp(ts: Any) -> str:
    """Format a timestamp float/int as ISO 8601 string."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, UTC).isoformat()
    return str(ts)


def _render_tome_export(
    meta: TomeMetadata, entries: list[TomeEntry], format: str
) -> str:
    """Render tome metadata and entries as JSON or Markdown."""
    if format == "json":
        data = {
            "metadata": {
                "id": meta.id,
                "created_at": meta.created_at,
                "cwd": meta.cwd,
                "parent_tome_id": meta.parent_tome_id,
                "active_leaf_id": meta.active_leaf_id,
                "schema_version": meta.schema_version,
            },
            "entries": [
                {
                    "id": e.id,
                    "parent_id": e.parent_id,
                    "type": e.type.value if hasattr(e.type, "value") else str(e.type),
                    "timestamp": _format_timestamp(e.timestamp),
                    "payload": e.payload,
                }
                for e in entries
            ],
        }
        return json.dumps(data, indent=2)
    elif format == "markdown":
        lines = [
            f"# Tome: {meta.id[:8]}",
            f"Created: {meta.created_at}",
            f"CWD: {meta.cwd}",
            "",
        ]
        for entry in entries:
            entry_type = (
                entry.type.value if hasattr(entry.type, "value") else str(entry.type)
            )
            lines.append(f"## {entry_type} ({_format_timestamp(entry.timestamp)})")
            lines.append("```json")
            lines.append(json.dumps(entry.payload, indent=2))
            lines.append("```")
            lines.append("")
        return "\n".join(lines)
    else:
        raise ValueError(f"Unknown format: {format}")


@tome_app.command("show")
def tome_show(
    tome_id: str = typer.Argument(..., help="Tome ID to show"),
    format: str | None = typer.Option(
        None, "--format", "-f", help="Output format (json, markdown)"
    ),
) -> None:
    """Show tome details."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    meta = ledger.open_tome(tome_id)
    if meta is None:
        console.print(format_error(f"Tome not found: {tome_id}"))
        raise typer.Exit(1) from None

    tome_entries = ledger.get_entries(meta.id)

    if format is not None:
        try:
            output_text = _render_tome_export(meta, tome_entries, format)
            console.print(output_text)
            return
        except ValueError:
            console.print(format_error(f"Unknown format: {format}"))
            raise typer.Exit(1) from None

    console.print(f"[bold]Tome:[/bold] {meta.id[:8]}")
    console.print(f"[bold]Created:[/bold] {meta.created_at}")
    console.print(f"[bold]CWD:[/bold] {meta.cwd}")
    console.print(f"[bold]Active Leaf:[/bold] {meta.active_leaf_id or '-'}")
    console.print(f"[bold]Entries:[/bold] {len(tome_entries)}")
    console.print()

    for entry in tome_entries:
        entry_type = (
            entry.type.value if hasattr(entry.type, "value") else str(entry.type)
        )
        console.print(f"  [{entry_type}] {_format_timestamp(entry.timestamp)}")
        console.print(f"    {entry.payload}")


@tome_app.command("export")
def tome_export(
    tome_id: str = typer.Argument(..., help="Tome ID to export"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Export format (json, markdown)"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file"),
) -> None:
    """Export a tome to JSON or Markdown."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    meta = ledger.open_tome(tome_id)
    if meta is None:
        console.print(format_error(f"Tome not found: {tome_id}"))
        raise typer.Exit(1) from None

    entries = ledger.get_entries(meta.id)

    try:
        output_text = _render_tome_export(meta, entries, format)
    except ValueError:
        console.print(format_error(f"Unknown format: {format}"))
        raise typer.Exit(1) from None

    if output:
        Path(output).write_text(output_text, encoding="utf-8")
        console.print(f"[green]Exported to {output}[/green]")
    else:
        console.print(output_text)


@tome_app.command("create")
def tome_create(
    cwd: str | None = typer.Option(
        None, "--cwd", help="Working directory (defaults to current)"
    ),
    parent: str | None = typer.Option(None, "--parent", help="Parent tome ID"),
) -> None:
    """Create a new tome."""
    tome_dir = get_tome_dir()

    if cwd is None:
        cwd = str(Path.cwd())

    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(cwd, parent_tome_id=parent)
    console.print(f"[green]Created tome: {meta.id[:8]}[/green]")
    console.print(f"[dim]File: {ledger.tome_file(meta.id)}[/dim]")


@tome_app.command("fork")
def tome_fork(
    tome_id: str = typer.Argument(..., help="Tome ID to fork from"),
    leaf_id: str = typer.Option(
        None, "--leaf", "-l", help="Leaf entry ID to fork at (default: current leaf)"
    ),
) -> None:
    """Fork a tome, creating a new branched tome."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    meta = ledger.open_tome(tome_id)
    if meta is None:
        console.print(format_error(f"Tome not found: {tome_id}"))
        raise typer.Exit(1)

    target_leaf = leaf_id or ledger.get_leaf_id(meta.id)
    if target_leaf is None:
        console.print(format_error("No leaf ID available. Specify --leaf."))
        raise typer.Exit(1)

    if ledger.get_entry(meta.id, target_leaf) is None:
        console.print(format_error(f"Leaf entry not found: {target_leaf}"))
        raise typer.Exit(1)

    try:
        forked_meta = ledger.create_branched_tome(
            parent_tome_id=meta.id,
            cwd=meta.cwd,
            fork_from_leaf_id=target_leaf,
        )
        console.print(f"[green]Forked tome: {forked_meta.id[:8]}[/green]")
        console.print(f"[dim]File: {ledger.tome_file(forked_meta.id)}[/dim]")
        console.print(f"[dim]Parent: {meta.id[:8]}[/dim]")
    except (KeyError, ValueError) as e:
        console.print(format_error(f"Failed to fork tome: {e}"))
        raise typer.Exit(1) from e


@tome_app.command("verify")
def tome_verify(
    tome_id: str = typer.Argument(..., help="Tome ID to verify"),
) -> None:
    """Verify integrity of a tome session file."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    report = ledger.verify_integrity(tome_id)
    if report.valid:
        console.print(f"[green]Tome {report.tome_id[:8]} is valid.[/green]")
        console.print(
            f"[dim]Total lines: {report.total_lines}, "
            f"Valid entries: {report.valid_entries_count}[/dim]"
        )
    else:
        console.print(
            format_error(
                f"Tome {report.tome_id} has {len(report.issues)} integrity issue(s):"
            )
        )
        for issue in report.issues:
            console.print(f"  [red]Line {issue.line_number}:[/red] {issue.message}")
        raise typer.Exit(1)
