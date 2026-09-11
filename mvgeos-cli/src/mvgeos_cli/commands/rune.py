from __future__ import annotations

import typer
from mvgeos_runes.installer import install_rune

from mvgeos_cli.console import format_error, get_console

console = get_console()

rune_app = typer.Typer(name="rune", help="Extension rune management")


@rune_app.callback(invoke_without_command=True)
def rune_callback(ctx: typer.Context) -> None:
    """Extension rune management."""
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@rune_app.command("install")
def rune_install(
    spec: str = typer.Argument(..., help="Rune name from marketplace or Git URL"),
) -> None:
    """Install an extension rune from the marketplace or a Git URL."""
    try:
        dest = install_rune(spec)
        console.print(f"[green]Successfully installed rune '{spec}' to {dest}[/green]")
    except Exception as exc:
        console.print(format_error(exc))
        raise typer.Exit(1) from exc
