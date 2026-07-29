from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

import typer
from mvgeos_agent.loop import MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    SummonerRequest,
)
from mvgeos_provider.models import get_model
from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_spells import (
    cast_bash,
    cast_edit,
    cast_find,
    cast_grep,
    cast_list,
    cast_read,
    cast_write,
)
from rich.console import Console

console = Console()

prompt_app = typer.Typer(name="prompt", help="Run a prompt through the Mvge agent")

SPELL_MAP = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}


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


async def _run_agent(
    incantation: str,
    model_id: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    mana_budget: int = 10000,
    contemplation_level: str = "medium",
    spells_enabled: list[str] | None = None,
) -> None:
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
        headers=model_info.headers,
    )

    realm = OpenRouterRealm(api_key=api_key, base_url=model.base_url)

    spells = _build_spells(spells_enabled or [])

    initial_invocation = SummonerRequest(
        role="user",
        content=incantation,
    )

    state = MvgeState(
        system_prompt=(
            "You are Mvge, a helpful AI coding agent. "
            "Use spells to interact with the filesystem and execute commands."
        ),
        model=model.__dict__,
        contemplation_level=ContemplationLevel(contemplation_level),
        spells=spells,
        invocations=[initial_invocation],
        mana_budget=mana_budget,
        max_tokens=max_tokens,
        temperature=temperature,
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
            model=model.__dict__,
            contemplation_level=contemplation_level,
        )
        if isinstance(result, MvgeResponse):
            console.print(f"\n[green]Done. Stop reason: {result.stop_reason}[/green]")
    finally:
        await realm.close()


@prompt_app.command()
def prompt(
    incantation: str = typer.Argument(..., help="The prompt/incantation to send"),
    model: str = typer.Option(
        "openrouter/anthropic/claude-3.5-sonnet",
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
    contemplation_level: str = typer.Option(
        "medium", "--contemplation", "-c", help="Contemplation level"
    ),
    spells: str = typer.Option(
        "bash,read,write,edit,find,list,grep",
        "--spells",
        "-s",
        help="Comma-separated list of enabled spells",
    ),
) -> None:
    """Run a prompt through the Mvge agent."""
    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key is None:
        console.print(
            "[red]API key required. Set OPENROUTER_API_KEY or use --api-key[/red]"
        )
        raise typer.Exit(1)

    spells_list = [s.strip() for s in spells.split(",") if s.strip()]

    asyncio.run(
        _run_agent(
            incantation=incantation,
            model_id=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            mana_budget=mana_budget,
            contemplation_level=contemplation_level,
            spells_enabled=spells_list,
        )
    )
