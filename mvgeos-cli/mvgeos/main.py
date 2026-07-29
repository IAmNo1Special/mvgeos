from __future__ import annotations

import typer
from rich.console import Console

from mvgeos.commands.config import config_app
from mvgeos.commands.prompt import prompt_app
from mvgeos.commands.tome import tome_app

console = Console()

app = typer.Typer(name="mvgeos", help="MvgeOS — a Python-based AI coding agent")
app.add_typer(config_app, name="config")
app.add_typer(prompt_app, name="prompt")
app.add_typer(tome_app, name="tome")


def main() -> None:
    app()
