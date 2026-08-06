from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    RegisteredCommand,
    RuneContext,
    RuneManifest,
    RuneShortcut,
    SigilHook,
    SpellDefinition,
)


class TestRuneRunnerSpells:
    def test_register_and_get_spells(self) -> None:
        runner = RuneRunner()
        spell = SpellDefinition(
            name="test_spell",
            description="A test spell",
            parameters={"type": "object"},
        )
        runner.register_spell(spell)
        spells = runner.get_all_registered_spells()
        assert len(spells) == 1
        assert spells[0].name == "test_spell"

    def test_first_registration_wins(self) -> None:
        runner = RuneRunner()
        spell1 = SpellDefinition(name="dup", description="first")
        spell2 = SpellDefinition(name="dup", description="second")
        runner.register_spell(spell1)
        runner.register_spell(spell2)
        spells = runner.get_all_registered_spells()
        assert len(spells) == 1
        assert spells[0].description == "first"

    def test_empty_spells(self) -> None:
        runner = RuneRunner()
        assert runner.get_all_registered_spells() == []

    def test_active_spells(self) -> None:
        runner = RuneRunner()
        runner.register_spell(SpellDefinition(name="a", description=""))
        runner.register_spell(SpellDefinition(name="b", description=""))
        assert runner.get_active_spells() == ["a", "b"]


class TestRuneRunnerCommands:
    def test_register_and_get_commands(self) -> None:
        runner = RuneRunner()

        def handler() -> None:
            return None

        cmd = RegisteredCommand(
            name="test_cmd", description="A command", handler=handler
        )
        runner.register_command(cmd)
        commands = runner.get_commands()
        assert len(commands) == 1
        assert commands[0].name == "test_cmd"

    def test_first_command_wins(self) -> None:
        runner = RuneRunner()
        runner.register_command(RegisteredCommand(name="dup", description="first"))
        runner.register_command(RegisteredCommand(name="dup", description="second"))
        assert len(runner.get_commands()) == 1
        assert runner.get_commands()[0].description == "first"


class TestRuneRunnerShortcuts:
    def test_register_and_get_shortcuts(self) -> None:
        runner = RuneRunner()
        shortcut = RuneShortcut(key="ctrl+k", description="Test", handler=lambda: None)
        runner.register_shortcut(shortcut)
        shortcuts = runner.get_shortcuts()
        assert len(shortcuts) == 1
        assert shortcuts[0].key == "ctrl+k"

    def test_duplicate_shortcut_logs_warning(self, caplog) -> None:
        runner = RuneRunner()
        shortcut1 = RuneShortcut(key="ctrl+k", description="First", handler=lambda: None)
        shortcut2 = RuneShortcut(key="ctrl+k", description="Second", handler=lambda: None)
        runner.register_shortcut(shortcut1)
        runner.register_shortcut(shortcut2)
        assert len(runner.get_shortcuts()) == 1
        assert "Duplicate shortcut registration skipped" in caplog.text


class TestRuneRunnerProviders:
    def test_register_provider(self) -> None:
        runner = RuneRunner()
        runner.register_provider("test", {"api_key": "xyz"})
        assert runner._providers["test"] == {"api_key": "xyz"}

    def test_first_provider_wins(self) -> None:
        runner = RuneRunner()
        runner.register_provider("test", {"api_key": "first"})
        runner.register_provider("test", {"api_key": "second"})
        assert runner._providers["test"]["api_key"] == "first"

    def test_get_registered_providers(self) -> None:
        runner = RuneRunner()
        assert runner.get_registered_providers() == {}
        runner.register_provider("a", {"key": 1})
        runner.register_provider("b", {"key": 2})
        providers = runner.get_registered_providers()
        assert providers["a"] == {"key": 1}
        assert providers["b"] == {"key": 2}


class TestRuneRunnerDispatch:
    @pytest.mark.asyncio
    async def test_emit_async_calls_handlers(self) -> None:
        runner = RuneRunner()
        handler = MagicMock()
        runner.register_handler(SigilHook.TURN_START, handler)
        await runner.emit_async(SigilHook.TURN_START, {"key": "value"})
        handler.assert_called_once_with({"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_async_async_handler(self) -> None:
        runner = RuneRunner()
        handler = AsyncMock()
        runner.register_handler(SigilHook.TURN_START, handler)
        await runner.emit_async(SigilHook.TURN_START, {"key": "value"})
        handler.assert_called_once_with({"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_chain_transforms_data(self) -> None:
        runner = RuneRunner()

        def add_tag(data: dict) -> dict:
            data["tagged"] = True
            return data

        runner.register_handler(SigilHook.CONTEXT_TRANSFORM, add_tag)
        result = await runner.emit_chain(SigilHook.CONTEXT_TRANSFORM, {"count": 1})
        assert result == {"count": 1, "tagged": True}

    @pytest.mark.asyncio
    async def test_emit_chain_multiple_handlers(self) -> None:
        runner = RuneRunner()

        def add_one(data: dict) -> dict:
            data["value"] = data.get("value", 0) + 1
            return data

        def double(data: dict) -> dict:
            data["value"] = data["value"] * 2
            return data

        runner.register_handler(SigilHook.CONTEXT_TRANSFORM, add_one)
        runner.register_handler(SigilHook.CONTEXT_TRANSFORM, double)
        result = await runner.emit_chain(SigilHook.CONTEXT_TRANSFORM, {"value": 1})
        assert result["value"] == 4

    @pytest.mark.asyncio
    async def test_emit_chain_no_handlers(self) -> None:
        runner = RuneRunner()
        result = await runner.emit_chain(SigilHook.CONTEXT_TRANSFORM, {"data": 1})
        assert result == {"data": 1}

    @pytest.mark.asyncio
    async def test_emit_first_returns_first_non_none(self) -> None:
        runner = RuneRunner()

        def handler1(data: dict) -> None:
            return None

        def handler2(data: dict) -> dict:
            return {"handled": True}

        runner.register_handler(SigilHook.BEFORE_SPELL_CAST, handler1)
        runner.register_handler(SigilHook.BEFORE_SPELL_CAST, handler2)
        result = await runner.emit_first(SigilHook.BEFORE_SPELL_CAST, {})
        assert result == {"handled": True}

    @pytest.mark.asyncio
    async def test_emit_first_no_match(self) -> None:
        runner = RuneRunner()

        def handler(data: dict) -> None:
            return None

        runner.register_handler(SigilHook.BEFORE_SPELL_CAST, handler)
        result = await runner.emit_first(SigilHook.BEFORE_SPELL_CAST, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_emit_block_blocks_on_dict_with_block_key(self) -> None:
        runner = RuneRunner()

        def blocker(data: dict) -> dict:
            return {"block": True, "reason": "not allowed"}

        runner.register_handler(SigilHook.BEFORE_SPELL_CAST, blocker)
        result = await runner.emit_block(SigilHook.BEFORE_SPELL_CAST, {})
        assert result is not None
        assert result["block"]

    @pytest.mark.asyncio
    async def test_emit_block_no_block(self) -> None:
        runner = RuneRunner()

        def handler(data: dict) -> dict | None:
            return None

        runner.register_handler(SigilHook.BEFORE_SPELL_CAST, handler)
        result = await runner.emit_block(SigilHook.BEFORE_SPELL_CAST, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_emit_object_handler(self) -> None:
        runner = RuneRunner()

        class HandlerObject:
            def turn_start(self, data: dict) -> None:
                self.called = True

        handler = HandlerObject()
        runner.register_handler(SigilHook.TURN_START, handler)
        await runner.emit_async(SigilHook.TURN_START, {})
        assert handler.called


class TestRuneRunnerLifecycle:
    @pytest.mark.asyncio
    async def test_load_runes_calls_factories(self) -> None:
        runner = RuneRunner()
        called = False

        def factory(api):
            nonlocal called
            called = True

        await runner.load_runes([factory])
        assert called

    @pytest.mark.asyncio
    async def test_load_runes_async_factory(self) -> None:
        runner = RuneRunner()
        called = False

        async def factory(api):
            nonlocal called
            called = True

        await runner.load_runes([factory])
        assert called

    @pytest.mark.asyncio
    async def test_load_runes_registers_spells(self) -> None:
        runner = RuneRunner()

        def factory(api):
            api.register_spell(
                SpellDefinition(name="rune_spell", description="From rune")
            )

        await runner.load_runes([factory])
        assert len(runner.get_all_registered_spells()) == 1
        assert runner.get_all_registered_spells()[0].name == "rune_spell"

    @pytest.mark.asyncio
    async def test_load_runes_registers_hooks(self) -> None:
        runner = RuneRunner()

        def factory(api):
            api.on(SigilHook.TURN_START, lambda d: None)

        await runner.load_runes([factory])
        assert len(runner._sigils.get_handlers(SigilHook.TURN_START)) == 1

    @pytest.mark.asyncio
    async def test_load_runes_registers_manifest_shortcuts(self) -> None:
        runner = RuneRunner()
        manifest = RuneManifest(
            name="test",
            version="1.0.0",
            description="Test",
            shortcuts=[
                RuneShortcut(key="ctrl+k", description="Clear"),
                RuneShortcut(key="ctrl+r", description="Reload"),
            ],
        )

        def factory(api):
            pass

        await runner.load_runes([factory], [manifest])
        shortcuts = runner.get_shortcuts()
        assert len(shortcuts) == 2
        assert shortcuts[0].key == "ctrl+k"
        assert shortcuts[1].key == "ctrl+r"

    @pytest.mark.asyncio
    async def test_load_runes_manifests_none(self) -> None:
        runner = RuneRunner()

        def factory(api):
            pass

        await runner.load_runes([factory], None)
        assert runner.get_shortcuts() == []
