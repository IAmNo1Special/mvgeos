from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import typer
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeMetadata
from rich.console import Console
from rich.table import Table

console = Console()
tome_app = typer.Typer()


def get_tome_dir() -> Path:
    agents_dir = Path(".agents/mvgeos")
    agents_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = agents_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


@tome_app.command("list")
def tome_list() -> None:
    """List all sessions (tomes)."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    table = Table(title="MvgeOS Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Created", style="green")
    table.add_column("CWD", style="yellow")
    table.add_column("Active Leaf", style="magenta")

    for meta in ledger._tomles.values():
        table.add_row(
            meta.id,
            meta.created_at[:19],
            meta.cwd,
            meta.active_leaf_id or "—",
        )

    console.print(table)


@tome_app.command("show")
def tome_show(tome_id: str = typer.Argument(..., help="Session ID to show")) -> None:
    """Show session details."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    meta = ledger.open_tome(tome_id)
    if meta is None:
        console.print(f"[red]Session not found: {tome_id}[/red]")
        raise typer.Exit(1)

    entries = ledger.get_entries(tome_id)

    console.print(f"[bold]Session:[/bold] {meta.id}")
    console.print(f"[bold]Created:[/bold] {meta.created_at}")
    console.print(f"[bold]CWD:[/bold] {meta.cwd}")
    console.print(f"[bold]Active Leaf:[/bold] {meta.active_leaf_id or '—'}")
    console.print(f"[bold]Entries:[/bold] {len(entries)}")
    console.print()

    for entry in entries:
        console.print(f"  [{entry.type.value}] {entry.timestamp:.3f}")
        console.print(f"    {entry.payload}")


@tome_app.command("export")
def tome_export(
    tome_id: str = typer.Argument(..., help="Session ID to export"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Export format (json, markdown)"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file"),
) -> None:
    """Export a session to JSON or Markdown."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    meta = ledger.open_tome(tome_id)
    if meta is None:
        console.print(f"[red]Session not found: {tome_id}[/red]")
        raise typer.Exit(1)

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
            f"# Session: {meta.id}",
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
    parent: str | None = typer.Option(None, "--parent", help="Parent session ID"),
) -> None:
    """Create a new session."""
    tome_dir = get_tome_dir()
    ledger = TomeLedger(tome_dir)

    if cwd is None:
        cwd = str(Path.cwd())

    meta = TomeMetadata(
        id=f"tome_{uuid.uuid4().hex[:12]}",
        created_at=datetime.now().isoformat(),
        cwd=cwd,
        parent_tome_id=parent,
    )

    ledger.create_tome(meta)
    console.print(f"[green]Created session: {meta.id}[/green]")
