from __future__ import annotations

import json
from pathlib import Path

import typer
from mvgeos_agent.constants import DEFAULT_TOME_DIR
from mvgeos_tome.ledger import TomeLedger
from rich.console import Console
from rich.table import Table

console = Console()
tome_app = typer.Typer()


def get_tome_dir() -> Path:
    tome_dir = DEFAULT_TOME_DIR
    tome_dir.mkdir(parents=True, exist_ok=True)
    return tome_dir


@tome_app.command("list")
def tome_list() -> None:
    """List all tomes."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    table = Table(title="MvgeOS Tomes")
    table.add_column("ID", style="cyan")
    table.add_column("Created", style="green")
    table.add_column("CWD", style="yellow")
    table.add_column("Active Leaf", style="magenta")

    for meta in ledger.list_tomes():
        table.add_row(
            meta.id,
            meta.created_at[:19],
            meta.cwd,
            meta.active_leaf_id or "\u2014",
        )

    console.print(table)


@tome_app.command("show")
def tome_show(tome_id: str = typer.Argument(..., help="Tome ID to show")) -> None:
    """Show tome details."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    meta = ledger.open_tome(tome_id)
    if meta is None:
        console.print(f"[red]Tome not found: {tome_id}[/red]")
        raise typer.Exit(1) from None

    tome_entries = ledger.get_entries(tome_id)

    console.print(f"[bold]Tome:[/bold] {meta.id}")
    console.print(f"[bold]Created:[/bold] {meta.created_at}")
    console.print(f"[bold]CWD:[/bold] {meta.cwd}")
    console.print(f"[bold]Active Leaf:[/bold] {meta.active_leaf_id or '\u2014'}")
    console.print(f"[bold]Entries:[/bold] {len(tome_entries)}")
    console.print()

    for entry in tome_entries:
        console.print(f"  [{entry.type.value}] {entry.timestamp:.3f}")
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
        console.print(f"[red]Tome not found: {tome_id}[/red]")
        raise typer.Exit(1) from None

    entries = ledger.get_entries(tome_id)

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
                    "type": e.type.value,
                    "timestamp": e.timestamp,
                    "payload": e.payload,
                }
                for e in entries
            ],
        }
        output_text = json.dumps(data, indent=2)
    elif format == "markdown":
        lines = [
            f"# Tome: {meta.id}",
            f"Created: {meta.created_at}",
            f"CWD: {meta.cwd}",
            "",
        ]
        for entry in entries:
            lines.append(f"## {entry.type.value} ({entry.timestamp:.3f})")
            lines.append("```json")
            lines.append(json.dumps(entry.payload, indent=2))
            lines.append("```")
            lines.append("")
        output_text = "\n".join(lines)
    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        raise typer.Exit(1)

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
    console.print(f"[green]Created tome: {meta.id}[/green]")
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
        console.print(f"[red]Tome not found: {tome_id}[/red]")
        raise typer.Exit(1)

    target_leaf = leaf_id or ledger.get_leaf_id(tome_id)
    if target_leaf is None:
        console.print("[red]No leaf ID available. Specify --leaf.[/red]")
        raise typer.Exit(1)

    if ledger.get_entry(tome_id, target_leaf) is None:
        console.print(f"[red]Leaf entry not found: {target_leaf}[/red]")
        raise typer.Exit(1)

    try:
        forked_meta = ledger.create_branched_tome(
            parent_tome_id=tome_id,
            cwd=meta.cwd,
            fork_from_leaf_id=target_leaf,
        )
        console.print(f"[green]Forked tome: {forked_meta.id}[/green]")
        console.print(f"[dim]File: {ledger.tome_file(forked_meta.id)}[/dim]")
        console.print(f"[dim]Parent: {tome_id}[/dim]")
    except (KeyError, ValueError) as e:
        console.print(f"[red]Failed to fork tome: {e}[/red]")
        raise typer.Exit(1) from e
