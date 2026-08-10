from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import typer
from coding_mvge.spells import (
    cast_bash,
    cast_edit,
    cast_find,
    cast_grep,
    cast_list,
    cast_read,
    cast_write,
)
from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.config_manager import ConfigManager
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    resolve_rune_paths,
)
from mvgeos_agent.loop import MvgeLoop
from mvgeos_agent.prompt_config import (
    build_system_prompt,
    ensure_config_files,
)
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    SummonerRequest,
)
from mvgeos_provider.models import get_model
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.loader import load_runes_from_paths
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext, RuneScope
from mvgeos_runes.watcher import RuneWatcher
from mvgeos_tome.ledger import TomeLedger
from rich.console import Console

from mvgeos_cli.commands.config import config_app
from mvgeos_cli.commands.setup import setup_app
from mvgeos_cli.commands.tome import tome_app

console = Console()


def _load_api_key_from_auth() -> str | None:
    """Load API key from ~/.agents/.mvgeos/auth/openrouter.json."""
    auth_path = Path("~/.agents/.mvgeos/auth/openrouter.json").expanduser()
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text(encoding="utf-8"))
            api_key = data.get("api_key")
            return api_key if isinstance(api_key, str) else None
        except json.JSONDecodeError, OSError:
            pass
    return None


app = typer.Typer(name="mvgeos", help="MvgeOS — a Python-based AI coding agent")


def _scope_for_path(path: Path) -> RuneScope:
    path_str = str(path)
    if ".mvgeos/runes" in path_str and "{agent_name}" not in path_str:
        return RuneScope.USER
    if "{agent_name}" in path_str:
        return RuneScope.AGENT
    return RuneScope.PROJECT


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
    session_dir: str | None,
    tui: bool,
    agent_name: str = DEFAULT_AGENT_NAME,
) -> None:
    # Create ConfigManager to resolve config from all layers
    config_manager = ConfigManager(agent_name=agent_name)

    # Apply CLI overrides if provided
    if model_id is not None:
        config_manager = config_manager.with_overrides(model=model_id)
    if temperature is not None:
        config_manager = config_manager.with_overrides(temperature=temperature)
    if max_tokens is not None:
        config_manager = config_manager.with_overrides(max_tokens=max_tokens)
    if contemplation_level is not None:
        config_manager = config_manager.with_overrides(
            contemplation_level=contemplation_level
        )
    if spells_enabled is not None:
        config_manager = config_manager.with_overrides(spells_enabled=spells_enabled)

    # Get resolved config
    resolved = config_manager.load()
    model_id = model_id or resolved["model"].value
    temperature = (
        temperature if temperature is not None else resolved["temperature"].value
    )
    max_tokens = max_tokens if max_tokens is not None else resolved["max_tokens"].value
    contemplation_level = contemplation_level or resolved["contemplation_level"].value
    spells_enabled = spells_enabled or resolved["spells_enabled"].value

    if incantation is None:
        if tui:
            from mvgeos_cli.commands.tui import run_tui

            await run_tui(
                model=model_id,
                api_key=api_key,
                spells=",".join(spells_enabled),
                extension_dir=extension_dir,
                resume=resume,
                provider=provider_name,
                temperature=temperature,
                max_tokens=max_tokens,
                contemplation=contemplation_level,
                session_dir=session_dir,
            )
            return

        from mvgeos_cli.commands.repl import run_repl

        await run_repl(
            model=model_id,
            api_key=api_key,
            spells=",".join(spells_enabled),
            extension_dir=extension_dir,
            resume=resume,
            provider=provider_name,
            temperature=temperature,
            max_tokens=max_tokens,
            contemplation=contemplation_level,
            session_dir=session_dir,
        )
        return

    provider_registry = RealmRegistry()

    ensure_config_files(agent_name)

    runner: RuneRunner | None = None
    watchers: list[RuneWatcher] = []

    runes_paths = resolve_rune_paths(agent_name, extension_dir)
    paths_with_scope = [(p, _scope_for_path(p)) for p in runes_paths]

    loads, diagnostics = load_runes_from_paths(paths_with_scope, agent_name)
    if loads:
        runner = RuneRunner()
        runner.bind_context(
            RuneContext(
                cwd=str(Path.cwd()),
                mode="cli",
                agent_name=agent_name,
                api_key=api_key,
            )
        )
        await runner.load_rune_loads(loads, diagnostics)
        for pname, pconfig in runner.get_registered_providers().items():
            if isinstance(pconfig, dict):
                provider_registry.register_provider(pname, pconfig)

        for path, _ in paths_with_scope:
            if path.exists():
                watcher = RuneWatcher(path, runner)
                await watcher.start()
                watchers.append(watcher)

    model_info = get_model(model_id)
    if model_info is None:
        console.print(f"[red]Unknown model: {model_id}[/red]")
        raise typer.Exit(1)

    model = Model(
        id=model_info.id,
        name=model_info.name,
        realm=model_info.realm,
        base_url=model_info.base_url,
        api_key=api_key,
        max_completion_mana=model_info.max_completion_mana,
        context_window=model_info.context_window,
        max_tokens=model_info.max_tokens,
        headers=dict(model_info.headers or {}),
    )

    provider_registry = RealmRegistry()
    realm = provider_registry.create_realm(model, api_key, provider_name)

    spells = []

    if runner is not None:
        # Only load seeker meta-tools, no preloaded spells
        rune_spells = runner.get_all_registered_spells()
        for rs in rune_spells:
            if rs.name in (
                "tool_search",
                "skill_search",
                "skill_execute",
                "mcp_search",
            ):
                spells.append(cast(MvgeSpell, rs))
        commands = runner.get_commands()
        if commands:
            cmd_names = ", ".join(c.name for c in commands)
            console.print(f"[dim]Registered commands: {cmd_names}[/dim]")
        shortcuts = runner.get_shortcuts()
        if shortcuts:
            sc_names = ", ".join(s.key for s in shortcuts)
            console.print(f"[dim]Registered shortcuts: {sc_names}[/dim]")
        ext_providers = provider_registry.get_registered_providers()
        if ext_providers:
            console.print(
                f"[dim]Registered providers: {', '.join(ext_providers)}[/dim]"
            )

    session_dir_path = Path(session_dir) if session_dir else _get_session_dir()
    ledger = TomeLedger(session_dir_path)
    agent_session: MvgeTome | None = None

    if resume:
        resume_path = Path(resume)
        if resume_path.exists():
            try:
                meta = ledger.open_tome(resume_path.stem)
                if meta is None:
                    raise ValueError("Tome not found")
                agent_session = MvgeTome(ledger, meta, runner)
                await agent_session.start(reason="resume")
                console.print(f"[dim]Resumed session: {meta.id}[/dim]")
            except (ValueError, FileNotFoundError) as e:
                console.print(
                    f"[yellow]Failed to resume session: {e}; creating new[/yellow]"
                )

    if agent_session is None:
        meta = ledger.create_tome(str(Path.cwd()))
        agent_session = MvgeTome(ledger, meta, runner)
        await agent_session.start(reason="startup")
        console.print(f"[dim]New session: {meta.id}[/dim]")

    initial_invocation = SummonerRequest(
        role="user",
        content=incantation,
    )

    state = MvgeState(
        system_prompt=build_system_prompt(
            spells=spells_enabled or [], cwd=str(Path.cwd())
        ),
        model=dataclasses.asdict(model),
        contemplation_level=ContemplationLevel(contemplation_level),
        spells=spells,
        invocations=[initial_invocation],
        max_tokens=max_tokens,
        temperature=temperature,
        rune_runner=runner,
        agent_session=agent_session,
    )

    loop = MvgeLoop(state)

    def stream_fn(invocations: list[MvgeInvocation]) -> AsyncIterator[RealmResponse]:
        return realm.stream(
            model=model,
            invocations=invocations,
            config=ChannelConfig(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )

    try:
        result = await loop.run(
            stream_fn=stream_fn,
            model=dataclasses.asdict(model),
            contemplation_level=contemplation_level,
        )
        if isinstance(result, MvgeResponse):
            console.print(f"\n[green]Done. Stop reason: {result.stop_reason}[/green]")
    finally:
        for watcher in watchers:
            await watcher.stop()
        if agent_session is not None:
            await agent_session.shutdown(reason="quit")
        await realm.close()


def _get_session_dir() -> Path:
    return Path("~/.agents/.mvgeos/tomes")


def _build_spells(enabled: list[str]) -> list[MvgeSpell]:
    spells = []
    for name in enabled:
        if name in SPELL_MAP:
            spells.append(
                MvgeSpell(
                    name=name,
                    description=f"Spell: {name}",
                    parameters={},
                )
            )
    return spells


SPELL_MAP = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}

console = Console()

app = typer.Typer(name="mvgeos", help="MvgeOS — a Python-based AI coding agent")


@app.callback(invoke_without_command=True)
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
    session_dir: str | None = typer.Option(
        None,
        "--session-dir",
        help="Custom session storage directory",
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

    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key is None:
        api_key = _load_api_key_from_auth()
    if api_key is None:
        console.print(
            "[red]API key required. Set OPENROUTER_API_KEY, "
            "add to ~/.agents/.mvgeos/auth/openrouter.json, or use --api-key[/red]"
        )
        raise typer.Exit(1)

    spells_list = (
        [s.strip() for s in spells.split(",") if s.strip()] if spells else None
    )

    asyncio.run(
        _run_agent(
            incantation=ctx.params.get("incantation"),
            model_id=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            contemplation_level=contemplation,
            spells_enabled=spells_list,
            extension_dir=extension_dir,
            resume=resume,
            provider_name=provider,
            session_dir=session_dir,
            tui=tui,
            agent_name=agent_name,
        )
    )


app.add_typer(config_app, name="config")
app.add_typer(tome_app, name="tome")
app.add_typer(setup_app, name="setup")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
