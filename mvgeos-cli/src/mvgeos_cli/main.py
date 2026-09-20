from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from typing import Any, cast

import typer
import typer._click as _click
from mvgeos_agent.auth import (
    load_api_key_from_auth,
    save_api_key_to_auth,
)
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.protocol import AgentFactory, MvgeAgent
from mvgeos_core.constants import (
    DEFAULT_AGENT_NAME,
)
from mvgeos_provider import NoRealmRegisteredError, get_default_realm_registry
from mvgeos_runes.installer import install_rune
from typer._click.parser import _split_opt
from typer.core import TyperGroup

from mvgeos_cli.agent_factory import create_agent, validate_api_key
from mvgeos_cli.approval_binding import (
    NO_SLOT_WARNING,
    approval_mode_notice,
    approval_presenter_bound,
    resolve_approval_mode,
)
from mvgeos_cli.approval_presenter import CliApprovalPresenter
from mvgeos_cli.approval_types import ApprovalMode
from mvgeos_cli.commands.build import build_app
from mvgeos_cli.commands.config import config_app
from mvgeos_cli.commands.info import info_app
from mvgeos_cli.commands.mvge import mvge_app
from mvgeos_cli.commands.repl import (
    _display_response,
    run_repl,
)
from mvgeos_cli.commands.rune import rune_app
from mvgeos_cli.commands.setup import DefaultCheckGroup, setup_app
from mvgeos_cli.commands.tome import tome_app
from mvgeos_cli.commands.tui import run_tui
from mvgeos_cli.console import (
    configure_streams,
    format_error,
    get_console,
    prompt_api_key,
)
from mvgeos_cli.dynamic_commands import (
    discover_installed_rune_commands,
    load_rune_cli_command,
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
    approval_mode: str | None = None,
) -> int:
    prompts_out = ([incantation] if incantation else []) + (prompts or [])
    mode: ApprovalMode = resolve_approval_mode(approval_mode)

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

        reg = get_default_realm_registry()
        active_realm = None
        with contextlib.suppress(Exception):
            _, active_realm = reg.resolve(
                model_id, api_key=api_key, provider_name=provider_name
            )

        if active_realm is not None and active_realm.is_router:
            target_realm = getattr(active_realm, "realm_name", "openrouter")
            providers = reg.get_providers_for_realm(target_realm)
            if len(providers) > 1 and not provider_name and "/" not in model_id:
                if sys.stdin.isatty() and sys.stdout.isatty() and not prompts_out:
                    console.print(
                        f"[yellow]Realm '{target_realm}' is a router. "
                        f"Available providers: {', '.join(providers[:10])}...[/yellow]"
                    )
                    prompted = input("Select provider: ").strip()
                    if prompted:
                        provider_name = prompted
                    else:
                        console.print(
                            format_error(
                                "Provider selection required for router realm."
                            )
                        )
                        return 1
                else:
                    console.print(
                        format_error(
                            f"Provider selection required for router realm "
                            f"'{target_realm}'. Specify --provider or use "
                            "provider/model format."
                        )
                    )
                    return 1
        elif active_realm is not None and not active_realm.is_router:
            if not provider_name:
                provider_name = getattr(active_realm, "realm_name", None)

        if approval_mode is not None:
            notice = approval_mode_notice(mode)
            if notice is not None:
                style = "yellow" if mode == "allow-all" else "dim"
                console.print(f"[{style}]{notice}[/{style}]")
        if tui and not prompts_out:
            console.print(
                "[dim]Note: approval prompts are unavailable in TUI mode; "
                "gated spell casts will be denied. Use the REPL for "
                "interactive approval.[/dim]"
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
                approval_mode=approval_mode,
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
        presenter = CliApprovalPresenter(mode=mode)
        # getattr: a custom agent_factory may return an agent without the
        # engine runner accessor; that is a missing slot (warn, fail
        # closed), not a crash.
        runner = getattr(agent, "runner", None)
        with approval_presenter_bound(runner, presenter) as bound:
            if not bound:
                console.print(f"[yellow]{NO_SLOT_WARNING}[/yellow]")
            return await _run_print_mode(agent, prompts_out)
    except NoRealmRegisteredError as exc:
        is_interactive = not prompts_out and not tui
        if is_interactive:
            try:
                answer = (
                    input(
                        "No Realm extension installed. Would you like to install "
                        "'openrouter-realm' from the marketplace now? [Y/n]: "
                    )
                    .strip()
                    .lower()
                )
            except (EOFError, KeyboardInterrupt):
                answer = "n"

            if answer in ("", "y", "yes"):
                try:
                    install_rune("openrouter-realm")
                    console.print(
                        "[green]Successfully installed 'openrouter-realm'. "
                        "Starting session...[/green]"
                    )
                    return await _run_agent(
                        incantation=incantation,
                        model_id=model_id,
                        api_key=api_key,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        contemplation_level=contemplation_level,
                        spells_enabled=spells_enabled,
                        extension_dir=extension_dir,
                        resume=resume,
                        provider_name=provider_name,
                        tome_dir=tome_dir,
                        tui=tui,
                        agent_name=agent_name,
                        prompts=prompts,
                        agent_factory=agent_factory,
                        approval_mode=approval_mode,
                    )
                except Exception as install_exc:
                    console.print(format_error(install_exc))
                    return 1

        console.print(format_error(exc))
        return 1
    except Exception as exc:
        console.print(format_error(exc))
        return 1
    finally:
        if agent is not None:
            await agent.close()


class MvgeosGroup(TyperGroup):
    def get_command(self, ctx: _click.Context, cmd_name: str) -> _click.Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        res = load_rune_cli_command(cmd_name)
        if res is not None:
            return cast(_click.Command, res)
        return None

    def list_commands(self, ctx: _click.Context) -> list[str]:
        base_cmds = super().list_commands(ctx)
        rune_cmds = list(discover_installed_rune_commands().keys())
        return sorted(set(base_cmds + rune_cmds))

    def invoke(self, ctx: _click.Context) -> Any:
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            first = args[0] if args else ""
            if not _split_opt(first)[0]:
                is_prompt = False
                cmd = self.get_command(ctx, first)
                if cmd is None:
                    is_prompt = True
                elif len(args) > 1 and not _split_opt(args[1])[0]:
                    subcommands = (
                        cmd.list_commands(ctx) if hasattr(cmd, "list_commands") else []
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
    approval_mode: str | None = typer.Option(
        None,
        "--approval-mode",
        help=(
            "One-run approval behavior for gated spell casts: "
            "deny, prompt, or allow-all. Never persisted; "
            "environment variables never grant approval."
        ),
    ),
) -> None:
    """Launch the MvgeOS interactive REPL, or run a single prompt."""
    if ctx.invoked_subcommand is not None:
        return

    if approval_mode is not None:
        try:
            resolve_approval_mode(approval_mode)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

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
                    "[green]Saved API key to ~/.agents/auth/openrouter.json[/green]"
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
            approval_mode=approval_mode,
        )
    )
    if code:
        raise typer.Exit(code)


app.add_typer(build_app, name="build")
app.add_typer(config_app, name="config")
app.add_typer(info_app, name="info")
app.add_typer(tome_app, name="tome")
app.add_typer(rune_app, name="rune")
app.add_typer(mvge_app, name="mvge")
app.add_typer(setup_app, name="setup", cls=DefaultCheckGroup)


def main() -> None:
    configure_streams()
    app()


if __name__ == "__main__":
    main()
