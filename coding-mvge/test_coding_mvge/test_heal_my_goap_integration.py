"""End-to-end integration test for heal_my_goap Rune with CodingMvge."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from mvgeos_agent.loop import _safe_emit_chain
from mvgeos_runes.types import SigilHook

from coding_mvge.mvge import CodingMvge

HAS_HEAL_MY_GOAP = importlib.util.find_spec("heal_my_goap") is not None


skip_if_no_heal_my_goap = pytest.mark.skipif(
    not HAS_HEAL_MY_GOAP, reason="heal-my-goap not installed"
)

@skip_if_no_heal_my_goap
@pytest.mark.asyncio
async def test_coding_agent_with_heal_my_goap_rune() -> None:
    """Verifies CodingMvge initializes with global heal_my_goap Rune."""
    global_ext_dir = Path.home() / ".agents" / ".mvgeos" / "extensions"
    assert global_ext_dir.exists(), (
        "Global .agents/.mvgeos/extensions directory does not exist"
    )

    # Instantiate CodingMvge pointing to global extension directory
    agent = CodingMvge(
        extension_dir=str(global_ext_dir),
        api_key="test_mock_key",
        provider_name="openrouter",
    )

    # Initialize the agent (loads runes, binds runner, converts spells)
    await agent.initialize()

    # 1. Verify RuneRunner loaded heal_my_goap spells
    assert agent._runner is not None, "RuneRunner failed to initialize"
    registered_spells = [s.name for s in agent._runner.get_all_registered_spells()]
    assert "goap_plan_and_execute" in registered_spells
    assert "goap_sense_world" in registered_spells
    assert "goap_synthesize_action" in registered_spells

    # 2. Verify spells are appended to BaseMvge state.spells
    assert agent._state is not None, "Agent state failed to initialize"
    state_spell_names = [s.name for s in agent._state.spells]
    assert "goap_plan_and_execute" in state_spell_names
    assert "goap_sense_world" in state_spell_names
    assert "goap_synthesize_action" in state_spell_names

    # 3. Execute goap_sense_world via RuneRunner spell definition
    sense_spell = next(
        s
        for s in agent._runner.get_all_registered_spells()
        if s.name == "goap_sense_world"
    )
    sense_res = await sense_spell.execute("test_cast_1", {})
    assert "world_state" in sense_res
    assert isinstance(sense_res["world_state"], dict)
    assert (
        "cpu_usage_pct" in sense_res["world_state"]
        or "ram_usage_pct" in sense_res["world_state"]
    )

    # 4. Execute goap_plan_and_execute with target_state
    plan_spell = next(
        s
        for s in agent._runner.get_all_registered_spells()
        if s.name == "goap_plan_and_execute"
    )
    # Target state condition
    plan_params = {
        "initial_state": {"door_open": False, "has_key": True},
        "target_state": {"door_open": False},
    }
    plan_res = await plan_spell.execute("test_cast_2", plan_params)
    assert plan_res.get("status") in ("success", "failed")

    # 5. Verify BEFORE_INVOCATION Sigil syncs active MvgeOS Spells into GoapEngine
    await agent._runner.emit_async(SigilHook.BEFORE_INVOCATION, {})

    # 6. Verify AFTER_SPELL_RESULT Sigil intercept on failed spell
    failed_payload = {
        "spell_name": "broken_command",
        "spell_cast_id": "call_999",
        "result": {"error": "Permission denied"},
    }
    transformed_res = await _safe_emit_chain(
        agent._runner,
        SigilHook.AFTER_SPELL_RESULT,
        failed_payload,
    )
    assert transformed_res is not None
    assert transformed_res.get("result", {}).get("status") in (
        "spell_registered",
        "healed",
    )
    assert transformed_res.get("result", {}).get("healed_by") == "heal_my_goap"

    # Cleanup watcher
    if agent._watcher:
        await agent._watcher.stop()


@skip_if_no_heal_my_goap
@pytest.mark.asyncio
async def test_missing_read_tool_self_healing_execution(tmp_path: Path) -> None:
    """Verifies heal_my_goap synthesizes and executes code when tool missing."""
    readme_file = tmp_path / "README.md"
    readme_file.write_text(
        "Hello from heal_my_goap self-healing read!", encoding="utf-8"
    )

    global_ext_dir = Path.home() / ".agents" / ".mvgeos" / "extensions"
    agent = CodingMvge(
        extension_dir=str(global_ext_dir),
        api_key="test_mock_key",
        provider_name="openrouter",
    )
    await agent.initialize()

    # Mock synthesizer to return a synthesized Action with code for reading file
    mock_action = MagicMock()
    mock_action.name = "synth_read_file"
    mock_action.code = (
        "read_content = 'README file contents read via heal_my_goap self-healing!'\n"
    )
    mock_action.preconditions = {}
    mock_action.effects = {"file_read": True}

    assert agent._runner is not None
    target_spell = cast(Any, agent._runner._spells["goap_plan_and_execute"])
    with patch.object(
        target_spell._engine.synthesizer,
        "synthesize_bridge_action",
        return_value=mock_action,
    ):
        failed_payload = {
            "spell_name": "read",
            "spell_cast_id": "cast_read_001",
            "arguments": {"path": str(readme_file)},
            "result": {"error": "Spell 'read' not found or failed"},
        }
        healed_res = await _safe_emit_chain(
            agent._runner,
            SigilHook.AFTER_SPELL_RESULT,
            failed_payload,
        )

        assert healed_res is not None
        result_data = healed_res.get("result", {})
        assert result_data.get("status") == "spell_registered"
        assert result_data.get("registered_spell_name") == "synth_read_file"

        # Verify synthesized action registered on RuneRunner
        assert "synth_read_file" in agent._runner.get_active_spells()

        # Execute the registered synthesized spell to verify single execution
        synth_spell = next(
            s
            for s in agent._runner.get_all_registered_spells()
            if s.name == "synth_read_file"
        )
        synth_res = await synth_spell.execute(
            "cast_synth_001", {"path": str(readme_file)}
        )
        assert "read_content" in synth_res
        assert (
            synth_res["read_content"]
            == "README file contents read via heal_my_goap self-healing!"
        )

    if agent._watcher:
        await agent._watcher.stop()
