"""Interactive validation script for heal_my_goap Rune."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from mvgeos_runes.types import SigilHook
from rich.console import Console
from rich.table import Table

from coding_mvge.mvge import CodingMvge

HAS_HEAL_MY_GOAP = importlib.util.find_spec("heal_my_goap") is not None


skip_if_no_heal_my_goap = pytest.mark.skipif(
    not HAS_HEAL_MY_GOAP, reason="heal-my-goap not installed"
)


@skip_if_no_heal_my_goap
@pytest.mark.asyncio
@pytest.mark.skip(
    reason="Requires local scratch_extensions with heal_my_goap rune installed"
)
async def test_interactive_demo() -> None:
    """Test version of interactive demo for CI."""
    console = Console()

    global_ext_dir = Path("scratch_extensions").resolve()
    console.print(f"[dim]Loading global extensions from: {global_ext_dir}[/dim]")

    # 1. Initialize CodingMvge
    agent = CodingMvge(
        extension_dir=str(global_ext_dir),
        api_key="mock_key",
        provider_name="openrouter",
    )
    await agent.initialize()
    console.print("[green][OK] CodingMvge initialized successfully[/green]")

    # 2. Inspect registered Spells
    runner = agent._runner
    assert runner is not None
    active_spells = runner.get_all_registered_spells()

    table = Table(title="Registered Rune Spells on RuneRunner")
    table.add_column("Spell Name", style="bold green")
    table.add_column("Description", style="dim")
    table.add_column("Execution Mode", style="yellow")

    for spell in active_spells:
        table.add_row(spell.name, spell.description, str(spell.execution_mode))

    console.print(table)

    # 3. Interactive Call: Flow 2 Self-Healing for Open Opera GX Prompt
    console.print(
        "\n[bold yellow]Testing Prompt:[/bold yellow] "
        '[bold green]"Open Opera GX browser"[/bold green]'
    )
    missing_opera_payload = {
        "spell_name": "open_opera_gx",
        "spell_cast_id": "cast_004",
        "arguments": {"app": "Opera GX"},
        "result": {"error": "Spell 'open_opera_gx' not found in Grimoire"},
    }

    # Step 1: Rune catches error, synthesizes action, registers new Spell
    flow2_instruction = await runner.emit_chain(
        SigilHook.AFTER_SPELL_RESULT, missing_opera_payload
    )
    console.print(
        "\n[bold cyan]Step 1: Sigil registers spell and instructs Agent:[/bold cyan]"
    )
    console.print_json(json.dumps(flow2_instruction, indent=2))

    # Step 2: Agent inspects Grimoire and finds newly registered Spell
    newly_registered_spell = next(
        (
            s
            for s in runner.get_all_registered_spells()
            if s.name == "synth_open_opera_gx"
        ),
        None,
    )
    assert newly_registered_spell is not None, (
        "Failed to find newly registered spell 'synth_open_opera_gx'"
    )

    console.print(
        "\n[bold green][OK] Registered spell found:[/bold green] "
        f"{newly_registered_spell.name}"
    )
    console.print(f"[dim]Description: {newly_registered_spell.description}[/dim]")

    # Step 3: Agent executes the newly registered spell 'synth_open_opera_gx'
    console.print(
        "\n[bold yellow]Step 2: Agent casts newly registered spell:[/bold yellow]"
    )
    spell_execution_res = await newly_registered_spell.execute(
        "cast_005", {"app": "Opera GX"}
    )
    console.print("[bold white]Execution Output from Registered Spell:[/bold white]")
    console.print_json(json.dumps(spell_execution_res, indent=2))

    # Step 4: Final Agent Answer synthesis
    console.print("\n[bold cyan]Final Agent Answer to User:[/bold cyan]")
    msg = spell_execution_res.get("message")
    console.print(f"[bold green]{msg}[/bold green]")

    # Cleanup watcher
    if agent._watcher:
        await agent._watcher.stop()

    console.print(
        "\n[bold green][OK] Flow 2 CLI test completed successfully![/bold green]"
    )


if __name__ == "__main__":
    asyncio.run(test_interactive_demo())
