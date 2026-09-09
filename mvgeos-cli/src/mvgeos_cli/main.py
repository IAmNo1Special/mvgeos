from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, cast

import typer
import typer._click as _click
from mvgeos_agent.auth import (
    load_api_key_from_auth,
    save_api_key_to_auth,
)
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
)
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.protocol import AgentFactory, MvgeAgent
from typer._click.parser import _split_opt
from typer.core import TyperGroup

from mvgeos_cli.agent_factory import create_agent, validate_api_key
from mvgeos_cli.commands.build import build_app
from mvgeos_cli.commands.config import config_app
from mvgeos_cli.commands.info import info_app
from mvgeos_cli.commands.repl import (
    _display_response,
    run_repl,
)
from mvgeos_cli.commands.setup import DefaultCheckGroup, setup_app
from mvgeos_cli.commands.tome import tome_app
from mvgeos_cli.commands.tui import run_tui
from mvgeos_cli.console import (
    configure_streams,
    format_error,
    get_console,
    prompt_api_key,
)

console = get_console()

_create_agent = create_agent


def _default_spells_from_config(resolved: dict[str, Any]) -> str:
    val = resolved["spells_enabled"].value
    if isinstance(val, list):
        return ",".join(val)
    return str(val)


async def _run_print_mode(agent: MvgeAgent, prompts: list[str]) -> int:
    try:
        for prompt in prompts:
            result = await agent.run(prompt)
            _display_response(result)
        return 0
    except Exception as exc:
        console.print(format_error(exc))
        return 1


async def _run_agent(
    incantation: str | None,
    model_id: str | None,
    api_key: str,
    temperature: float | None,
    max_tokens: int | None,
    contemplation_level: str | None,
    spells_enabled: list[str] | None,
    extension_dir: str | None,
    resume: str | None,
    provider_name: str | None,
    tome_dir: str | None,
    tui: bool,
    agent_name: str = DEFAULT_AGENT_NAME,
    prompts: list[str] | None = None,
    agent_factory: AgentFactory | None = None,
) -> int:
    prompts_out = ([incantation] if incantation else []) + (prompts or [])

    overrides: dict[str, Any] = {}
    if model_id is not None:
        overrides["model"] = model_id
    if temperature is not None:
        overrides["temperature"] = temperature
    if max_tokens is not None:
        overrides["max_tokens"] = max_tokens
    if contemplation_level is not None:
        overrides["contemplation_level"] = contemplation_level
    if spells_enabled is not None:
        overrides["spells_enabled"] = spells_enabled

    agent: MvgeAgent | None = None
    try:
        env = MvgeEnvironment.resolve(
            agent_name=agent_name,
            extension_dir=extension_dir,
            overrides=overrides,
        )
        resolved = env.config
        model_id = model_id or str(resolved["model"].value)
        temperature = (
            temperature
            if temperature is not None
            else float(resolved["temperature"].value)
        )
        max_tokens = (
            max_tokens if max_tokens is not None else int(resolved["max_tokens"].value)
        )
        contemplation_level = contemplation_level or str(
            resolved["contemplation_level"].value
        )
        spells_joined = (
            ",".join(spells_enabled)
            if spells_enabled is not None
            else _default_spells_from_config(resolved)
        )

        if not prompts_out:
            if tui:
                await run_tui(
                    model=model_id,
                    api_key=api_key,
                    spells=spells_joined,
                    extension_dir=extension_dir,
                    resume=resume,
                    provider=provider_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    contemplation=contemplation_level,
                    tome_dir=tome_dir,
                    agent_name=agent_name,
                    agent_factory=agent_factory,
                )
                return 0

            await run_repl(
                model=model_id,
                api_key=api_key,
                spells=spells_joined,
                extension_dir=extension_dir,
                resume=resume,
                provider=provider_name,
                temperature=temperature,
                max_tokens=max_tokens,
                contemplation=contemplation_level,
                tome_dir=tome_dir,
                agent_name=agent_name,
                agent_factory=agent_factory,
            )
            return 0

        validate_api_key(api_key)
        agent = await _create_agent(
            model=model_id,
            api_key=api_key,
            spells=spells_joined,
            extension_dir=extension_dir,
            tome_dir=tome_dir,
            resume=resume,
            provider=provider_name,
            temperature=temperature,
            max_tokens=max_tokens,
            contemplation=contemplation_level,
            agent_name=agent_name,
            agent_factory=agent_factory,
        )
        return await _run_print_mode(agent, prompts_out)
    except Exception as exc:
        console.print(format_error(exc))
        return 1
    finally:
        if agent is not None:
            await agent.close()


class MvgeosGroup(TyperGroup):
    def invoke(self, ctx: _click.Context) -> Any:
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            first = args[0] if args else ""
            if not _split_opt(first)[0]:
                is_prompt = False
                if first not in self.commands:
                    is_prompt = True
                elif len(args) > 1 and not _split_opt(args[1])[0]:
                    cmd = self.get_command(ctx, first)
                    if cmd is not None:
                        subcommands = (
                            cmd.list_commands(ctx)
                            if hasattr(cmd, "list_commands")
                            else []
                        )
                        is_leaf = not bool(subcommands)
                        params = getattr(cmd, "params", [])
                        has_positional = any(
                            getattr(p, "param_type_name", None) == "argument"
                            for p in params
                        )
                        if is_leaf and not has_positional:
                            is_prompt = True

                if is_prompt:
                    ctx.meta["prompts"] = list(args)
                    ctx.args = []
                    ctx._protected_args = []
                    with ctx:
                        return _click.Command.invoke(self, ctx)
        return TyperGroup.invoke(self, ctx)


app = typer.Typer(
    name="mvgeos",
    help="MvgeOS - a Python-based AI coding agent",
    cls=MvgeosGroup,
)


@app.callback(invoke_without_command=True, cls=MvgeosGroup)
def _repl_callback(
    ctx: typer.Context,
    incantation: str | None = typer.Option(
        None, "--incantation", help="Prompt to send (if omitted, starts REPL)"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model to use"),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="OpenRouter API key (or set OPENROUTER_API_KEY env)",
    ),
    temperature: float | None = typer.Option(
        None, "--temperature", "-t", help="Sampling temperature"
    ),
    max_tokens: int | None = typer.Option(None, "--max-tokens", help="Maximum tokens"),
    contemplation: str | None = typer.Option(
        None, "--contemplation", "-c", help="Contemplation level"
    ),
    spells: str | None = typer.Option(
        None,
        "--spells",
        "-s",
        help="Comma-separated list of enabled spells",
    ),
    extension_dir: str | None = typer.Option(
        None,
        "--extension-dir",
        "-e",
        help="Path to extension runes directory",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        "-r",
        help="Path to a session JSONL file to resume",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="Provider name (from extension registration)",
    ),
    tome_dir: str | None = typer.Option(
        None,
        "--tome-dir",
        help="Custom tome storage directory",
    ),
    tui: bool = typer.Option(
        False,
        "--tui",
        help="Use the full-screen TUI instead of the streaming REPL",
    ),
    agent_name: str = typer.Option(
        DEFAULT_AGENT_NAME,
        "--agent-name",
        help="Agent name for agent-specific rune directory",
    ),
) -> None:
    """Launch the MvgeOS interactive REPL, or run a single prompt."""
    if ctx.invoked_subcommand is not None:
        return

    if api_key is None and model and model.startswith("google/"):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key is None and model and model.startswith("ollama/"):
        api_key = ""
    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key is None:
        api_key = load_api_key_from_auth()
    if api_key is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            prompted_key = prompt_api_key(console)
            if prompted_key:
                save_api_key_to_auth(prompted_key)
                console.print(
                    "[green]Saved API key to "
                    "~/.agents/.mvgeos/auth/openrouter.json[/green]"
                )
                api_key = prompted_key
        if api_key is None:
            console.print(
                format_error(
                    "API key required. Set OPENROUTER_API_KEY, "
                    "run 'mvgeos setup', or use --api-key"
                )
            )
            raise typer.Exit(1)

    spells_list = (
        [s.strip() for s in spells.split(",") if s.strip()] if spells else None
    )

    prompts = cast("list[str] | None", ctx.meta.get("prompts"))

    code = asyncio.run(
        _run_agent(
            incantation=incantation,
            model_id=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            contemplation_level=contemplation,
            spells_enabled=spells_list,
            extension_dir=extension_dir,
            resume=resume,
            provider_name=provider,
            tome_dir=tome_dir,
            tui=tui,
            agent_name=agent_name,
            prompts=prompts,
        )
    )
    if code:
        raise typer.Exit(code)


app.add_typer(build_app, name="build")
app.add_typer(config_app, name="config")
app.add_typer(info_app, name="info")
app.add_typer(tome_app, name="tome")
app.add_typer(setup_app, name="setup", cls=DefaultCheckGroup)


def main() -> None:
    configure_streams()
    app()


if __name__ == "__main__":
    main()
