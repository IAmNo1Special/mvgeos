"""Integration test for rune loading and execution framework."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.sigils import SigilRegistry
from mvgeos_runes.types import (
    RuneContext,
    RuneManifest,
    SigilHook,
    SpellDefinition,
)


class _TestSpell(SpellDefinition):
    """Test spell that tracks execution."""

    def __init__(self, name: str, description: str = "Test spell"):
        super().__init__(
            name=name,
            description=description,
            parameters={"type": "object", "properties": {}},
        )
        self.executed = False
        self.last_params = None

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        self.executed = True
        self.last_params = params
        return {"status": "success", "result": f"executed {self.name}"}


class FakeRuneFactory:
    """Factory that creates a test rune with known spells."""

    @staticmethod
    async def create(api: Any) -> None:
        # This would normally be in a rune.py file
        pass


def test_rune_runner_basic():
    """Test basic RuneRunner functionality."""
    runner = RuneRunner()
    runner.bind_context(
        RuneContext(cwd="/test", mode="test", agent_name="test", api_key="test")
    )

    # Test spell registration
    spell = _TestSpell("test_spell", "A test spell")
    runner.register_spell(spell)

    spells = runner.get_all_registered_spells()
    assert len(spells) == 1
    assert spells[0].name == "test_spell"

    # Test duplicate registration
    runner.register_spell(spell)
    assert len(runner.get_all_registered_spells()) == 1


def test_sigil_registry():
    """Test sigil hook registry."""
    registry = SigilRegistry()

    def handler(data):
        return "handled"

    registry.register("before_test", lambda d: "result")
    handlers = registry.get_handlers("before_test")
    assert len(handlers) == 1


def test_spell_definition():
    """Test SpellDefinition basic functionality."""
    spell = SpellDefinition(
        name="test",
        description="Test spell",
        parameters={"type": "object", "properties": {}},
    )
    assert spell.name == "test"
    assert spell.description == "Test spell"
    assert spell.parameters == {"type": "object", "properties": {}}

    # Test execute raises NotImplementedError
    import asyncio

    import pytest

    async def test_execute():
        with pytest.raises(NotImplementedError):
            await spell.execute("cast-1", {})

    asyncio.run(test_execute())


def test_rune_manifest():
    """Test RuneManifest creation."""
    manifest = RuneManifest(
        name="test_rune",
        version="1.0.0",
        description="Test rune",
        hooks=[],
        entry_point="main.py",
        shortcuts=[],
    )
    assert manifest.name == "test_rune"
    assert manifest.version == "1.0.0"
    assert manifest.description == "Test rune"


def test_sigil_hook_enum():
    """Test SigilHook enum values."""
    assert SigilHook.AGENT_START.value == "agent_start"
    assert SigilHook.BEFORE_INVOCATION.value == "before_invocation"
    assert SigilHook.AFTER_INVOCATION.value == "after_invocation"
    assert SigilHook.BEFORE_SPELL_CAST.value == "before_spell_cast"


# Integration test with temporary rune directory
@pytest.mark.asyncio
async def test_load_runes_from_temp_dir(tmp_path):
    """Test loading runes from a temporary directory."""
    rune_dir = tmp_path / "test_rune"
    rune_dir.mkdir()

    manifest_data = {
        "name": "test_rune",
        "version": "1.0.0",
        "description": "Test rune",
        "entry_point": "rune.py",
        "hooks": ["before_invocation", "after_invocation"],
    }

    manifest_file = rune_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    # Create a simple rune.py
    rune_py = rune_dir / "rune.py"
    rune_py.write_text("""
from mvgeos_runes.rune_api import RuneAPI
from mvgeos_runes.types import SpellDefinition

class TestSpell(SpellDefinition):
    async def execute(self, spell_cast_id, params, signal=None, on_update=None):
        return {"status": "ok"}

def rune_factory(api):
    api.register_spell(TestSpell(name="test_spell", description="Test"))
""")

    manifest = load_manifest(rune_dir)
    assert manifest is not None
    assert manifest.name == "test_rune"

    runner = RuneRunner()
    runner.bind_context(
        RuneContext(cwd="/tmp", mode="test", agent_name="test", api_key="")
    )
    await runner.load_runes([], [manifest])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
