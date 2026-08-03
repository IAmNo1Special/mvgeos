from __future__ import annotations

import asyncio
import dataclasses
import os
from collections.abc import AsyncGenerator
from pathlib import Path

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
from mvgeos_agent.loop import MvgeLoop
from mvgeos_agent.prompt_config import (
    build_system_prompt,
    ensure_config_files,
)
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    SummonerRequest,
)
from mvgeos_provider.models import get_model
from mvgeos_provider.registry import ProviderRegistry
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.loader import load_factories, load_manifests
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext
from mvgeos_runes.watcher import RuneWatcher
from mvgeos_tome.ledger import TomeLedger
from rich.console import Console

from mvgeos_cli import DEFAULT_MODEL
from mvgeos_cli.commands.config import config_app
from mvgeos_cli.commands.tome import tome_app

console = Console()

app = typer.Typer(name="mvgeos", help="MvgeOS — a Python-based AI coding agent")


async def _run_agent(
    incantation: str | None,
    model_id: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    mana_budget: int,
    contemplation_level: str,
    spells_enabled: list[str],
    extension_dir: str | None,
    resume: str | None,
    provider_name: str | None,
    session_dir: str | None,
    tui: bool,
) -> None:
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
                mana_budget=mana_budget,
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
            mana_budget=mana_budget,
            contemplation=contemplation_level,
            session_dir=session_dir,
        )
        return

    provider_registry = ProviderRegistry()

    ensure_config_files("coding-agent")

    runner: RuneRunner | None = None
    watcher: RuneWatcher | None = None

    if extension_dir:
        ext_path = Path(extension_dir)
        if ext_path.exists():
            runner = RuneRunner()
            runner.bind_context(RuneContext(cwd=str(ext_path), mode="cli"))
            manifests = load_manifests(ext_path)
            factories = load_factories(ext_path)
            await runner.load_runes(factories, manifests)
            for pname, pconfig in runner.get_registered_providers().items():
                if isinstance(pconfig, dict):
                    ProviderRegistry().register_provider(pname, pconfig)
            watcher = RuneWatcher(ext_path, runner)
            await watcher.start()

    model_info = get_model(model_id)
    if model_info is None:
        console.print(f"[red]Unknown model: {model_id}[/red]")
        raise typer.Exit(1)

    model = Model(
        id=model_info.id,
        name=model_info.name,
        realm=model_info.realm,
        provider=model_info.provider,
        base_url=model_info.base_url,
        api_key=api_key,
        mana_limit=model_info.mana_limit,
        context_window=model_info.context_window,
        max_tokens=model_info.max_tokens,
        headers=dict(model_info.headers or {}),
    )

    provider_registry = ProviderRegistry()
    realm = provider_registry.create_realm(model, api_key, provider_name)

    spells = _build_spells(spells_enabled)

    if runner is not None:
        rune_spells = runner.get_all_registered_spells()
        for rs in rune_spells:
            spells.append(
                MvgeSpell(
                    name=rs.name,
                    description=rs.description,
                    parameters=rs.parameters,
                )
            )
        commands = runner.get_commands()
        if commands:
            cmd_names = ", ".join(c.name for c in commands)
            console.print(f"[dim]Registered commands: {cmd_names}[/dim]")
        shortcuts = runner.get_shortcuts()
        if shortcuts:
            sc_names = ", ".join(s.key for s in shortcuts)
            console.print(f"[dim]Registered shortcuts: {sc_names}[/dim]")
        ext_providers = ProviderRegistry().get_registered_providers()
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
        mana_budget=mana_budget,
        max_tokens=max_tokens,
        temperature=temperature,
        rune_runner=runner,
        agent_session=agent_session,
    )

    loop = MvgeLoop(state)

    async def stream_fn() -> AsyncGenerator[RealmResponse]:
        async for response in realm.stream(
            model=model,
            invocations=state.invocations,
            config=ChannelConfig(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                mana_limit=mana_budget,
            ),
        ):
            yield response

    try:
        result = await loop.run(
            stream_fn=stream_fn(),
            model=dataclasses.asdict(model),
            contemplation_level=contemplation_level,
        )
        if isinstance(result, MvgeResponse):
            console.print(f"\n[green]Done. Stop reason: {result.stop_reason}[/green]")
    finally:
        if watcher is not None:
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
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="Model to use",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="OpenRouter API key (or set OPENROUTER_API_KEY env)",
    ),
    temperature: float = typer.Option(
        0.7, "--temperature", "-t", help="Sampling temperature"
    ),
    max_tokens: int = typer.Option(4096, "--max-tokens", help="Maximum tokens"),
    mana_budget: int = typer.Option(10000, "--mana", help="Mana budget"),
    contemplation: str = typer.Option(
        "medium", "--contemplation", "-c", help="Contemplation level"
    ),
    spells: str = typer.Option(
        "bash,read,write,edit,find,list,grep",
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
) -> None:
    """Launch the MvgeOS interactive REPL, or run a single prompt."""
    if ctx.invoked_subcommand is not None:
        return

    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key is None:
        console.print(
            "[red]API key required. Set OPENROUTER_API_KEY or use --api-key[/red]"
        )
        raise typer.Exit(1)

    asyncio.run(
        _run_agent(
            incantation=ctx.params.get("incantation"),
            model_id=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            mana_budget=mana_budget,
            contemplation_level=contemplation,
            spells_enabled=[s.strip() for s in spells.split(",") if s.strip()],
            extension_dir=extension_dir,
            resume=resume,
            provider_name=provider,
            session_dir=session_dir,
            tui=tui,
        )
    )


app.add_typer(config_app, name="config")
app.add_typer(tome_app, name="tome")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
