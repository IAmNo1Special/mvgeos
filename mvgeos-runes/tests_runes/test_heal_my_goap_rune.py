from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvgeos_runes.loader import load_factory_from_manifest, load_manifest
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook


@pytest.fixture
def rune_dir(tmp_path: Path) -> Path:
    """Fixture to create a temporary heal_my_goap rune directory."""
    r_dir = tmp_path / "heal_my_goap"
    r_dir.mkdir()

    manifest_data = {
        "name": "heal_my_goap",
        "version": "0.1.0",
        "description": "Zero-token GOAP planning & self-healing Rune",
        "entry_point": "rune.py",
        "hooks": ["session_start", "after_spell_result"],
    }
    (r_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    return r_dir


def test_heal_my_goap_manifest_loading(rune_dir: Path) -> None:
    """Verifies that the heal_my_goap manifest loads correctly."""
    manifest = load_manifest(rune_dir)
    assert manifest is not None
    assert manifest.name == "heal_my_goap"
    assert manifest.version == "0.1.0"
    assert SigilHook.AFTER_SPELL_RESULT in manifest.hooks


@pytest.mark.asyncio
async def test_rune_factory_registers_spells_and_sigils(rune_dir: Path) -> None:
    """Verifies rune_factory registers spells and AFTER_SPELL_RESULT sigil."""
    rune_py_content = """
import os
from typing import Any
from mvgeos_runes.rune_api import RuneAPI
from mvgeos_runes.types import ExecutionMode, SigilHook, SpellDefinition
from heal_my_goap.engine import GoapEngine
from heal_my_goap.models import ExecutionResult, WorldState, goal
from heal_my_goap.sensors import SystemSensors


class GoapPlanAndExecuteSpell(SpellDefinition):
    def __init__(self, engine: GoapEngine) -> None:
        super().__init__(
            name="goap_plan_and_execute",
            description="Executes a GOAP plan.",
            parameters={
                "type": "object",
                "properties": {"target_state": {"type": "object"}},
            },
        )
        self._engine = engine

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        raw_initial = params.get("initial_state")
        start_state = (
            SystemSensors().sample()
            if raw_initial is None
            else WorldState(**raw_initial)
        )
        target_goal = goal(**params["target_state"])
        try:
            res = await self._engine.arun(start_state, target_goal)
            return {"status": "success", "final_state": res.final_state}
        except Exception as err:
            return {"status": "failed", "error": str(err)}


class GoapSenseWorldSpell(SpellDefinition):
    def __init__(self) -> None:
        super().__init__(
            name="goap_sense_world",
            description="Reads live system metrics.",
            parameters={"type": "object"},
        )

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        sensors = SystemSensors()
        return {"world_state": sensors.sample().to_dict()}


class GoapSynthesizeActionSpell(SpellDefinition):
    def __init__(self, engine: GoapEngine) -> None:
        super().__init__(
            name="goap_synthesize_action",
            description="Synthesizes a missing action.",
            parameters={"type": "object"},
        )
        self._engine = engine

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return {"status": "synthesized"}


def rune_factory(api: RuneAPI) -> None:
    if "OPENROUTER_API_KEY" not in os.environ:
        auth_file = Path.home() / ".agents" / ".mvgeos" / "auth" / "openrouter.json"
        if auth_file.exists():
            try:
                data = json.loads(auth_file.read_text(encoding="utf-8"))
                if "api_key" in data:
                    os.environ["OPENROUTER_API_KEY"] = data["api_key"]
            except Exception:
                pass

    engine = GoapEngine()
    api.register_spell(GoapPlanAndExecuteSpell(engine))
    api.register_spell(GoapSenseWorldSpell())
    api.register_spell(GoapSynthesizeActionSpell(engine))

    async def on_after_spell_result(payload: dict[str, Any]) -> dict[str, Any] | None:
        result = payload.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            spell_name = payload.get("spell_name", "unknown")
            api.send_message(
                f"[Rune: heal_my_goap] Intercepted failure in '{spell_name}'."
            )
            return {
                "result": {
                    "status": "spell_registered",
                    "original_error": result.get("error"),
                    "healed_by": "heal_my_goap",
                }
            }
        return None

    api.on(SigilHook.AFTER_SPELL_RESULT, on_after_spell_result)
"""
    (rune_dir / "rune.py").write_text(rune_py_content, encoding="utf-8")

    manifest = load_manifest(rune_dir)
    assert manifest is not None
    factory = load_factory_from_manifest(manifest, rune_dir)
    assert factory is not None

    runner = RuneRunner()
    await runner.load_runes([factory], [manifest])

    spells = runner.get_active_spells()
    assert "goap_plan_and_execute" in spells
    assert "goap_sense_world" in spells
    assert "goap_synthesize_action" in spells

    fail_payload = {
        "spell_name": "broken_tool",
        "result": {"error": "Connection reset"},
    }
    transformed = await runner.emit_chain(SigilHook.AFTER_SPELL_RESULT, fail_payload)
    assert transformed is not None
    assert transformed.get("result", {}).get("status") == "spell_registered"


@pytest.mark.asyncio
async def test_global_heal_my_goap_rune_loading() -> None:
    """Verifies loading installed global Rune at ~/.agents/.mvgeos/extensions/."""
    global_rune_dir = (
        Path.home() / ".agents" / ".mvgeos" / "extensions" / "heal_my_goap"
    )
    assert global_rune_dir.exists()

    manifest = load_manifest(global_rune_dir)
    assert manifest is not None
    assert manifest.name == "heal_my_goap"

    factory = load_factory_from_manifest(manifest, global_rune_dir)
    assert factory is not None

    runner = RuneRunner()
    await runner.load_runes([factory], [manifest])

    active_spells = runner.get_active_spells()
    assert "goap_plan_and_execute" in active_spells
    assert "goap_sense_world" in active_spells
    assert "goap_synthesize_action" in active_spells
