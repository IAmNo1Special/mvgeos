from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    RegisteredCommand,
    RuneContext,
    RuneLoad,
    RuneManifest,
    RuneScope,
    RuneShortcut,
    SigilHook,
    SkillDiagnostic,
    SkillDiagnosticKind,
    SkillLoad,
    SkillManifest,
    SkillScope,
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

    def test_first_registration_wins(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        spell1 = SpellDefinition(name="dup", description="first")
        spell2 = SpellDefinition(name="dup", description="second")
        assert runner.register_spell(spell1) is True
        assert runner.register_spell(spell2) is False
        spells = runner.get_all_registered_spells()
        assert len(spells) == 1
        assert spells[0].description == "first"
        assert "Duplicate spell registration skipped: dup" in caplog.text

    def test_override_registration(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        spell1 = SpellDefinition(name="dup", description="first")
        spell2 = SpellDefinition(name="dup", description="second")
        assert runner.register_spell(spell1) is True
        with caplog.at_level(logging.DEBUG):
            assert runner.register_spell(spell2, override=True) is True
        spells = runner.get_all_registered_spells()
        assert len(spells) == 1
        assert spells[0].description == "second"
        assert "Overwriting existing spell registration" in caplog.text
        assert "Duplicate spell registration skipped" not in caplog.text

    def test_empty_spells(self) -> None:
        runner = RuneRunner()
        assert runner.get_all_registered_spells() == []

    def test_active_spells(self) -> None:
        runner = RuneRunner()
        runner.register_spell(SpellDefinition(name="a", description=""))
        runner.register_spell(SpellDefinition(name="b", description=""))
        assert runner.get_active_spells() == ["a", "b"]

    def test_active_spells_seeded_with_all_registered(self) -> None:
        runner = RuneRunner()
        runner.register_spell(SpellDefinition(name="tool_search", description=""))
        runner.register_spell(SpellDefinition(name="bash", description=""))
        # Default active set = all registered rune spells
        assert set(runner.get_active_spells()) == {"tool_search", "bash"}

    def test_set_active_spells_narrows(self) -> None:
        runner = RuneRunner()
        runner.register_spell(SpellDefinition(name="tool_search", description=""))
        runner.register_spell(SpellDefinition(name="bash", description=""))
        runner.set_active_spells(["tool_search"])
        assert runner.get_active_spells() == ["tool_search"]

    def test_set_active_spells_widens_beyond_registered(self) -> None:
        runner = RuneRunner()
        runner.register_spell(SpellDefinition(name="tool_search", description=""))
        # A rune may widen the active set with names not yet registered
        # (e.g. tool_search discovering a spell at runtime).
        runner.set_active_spells(["tool_search", "discovered_tool"])
        assert set(runner.get_active_spells()) == {"tool_search", "discovered_tool"}

    def test_register_spell_after_set_active_does_not_rewiden(self) -> None:
        runner = RuneRunner()
        runner.register_spell(SpellDefinition(name="tool_search", description=""))
        runner.set_active_spells(["tool_search"])
        runner.register_spell(SpellDefinition(name="bash", description=""))
        # Once a rune has pinned the active set, later registrations stay out.
        assert runner.get_active_spells() == ["tool_search"]


class TestRuneRunnerActiveSpellsComposition:
    """The active set is the union of each rune's own contribution.

    A rune that pins its active set (via ``set_active_spells``) only narrows or
    freezes its own contribution; it must not lock out spells contributed by
    other runes.
    """

    def test_second_rune_registers_after_first_pins_still_active(self) -> None:
        runner = RuneRunner()
        runner.register_spell(
            SpellDefinition(name="a", description=""), rune_name="rune_a"
        )
        runner.set_active_spells(["a"], rune_name="rune_a")
        # A different rune registers a spell after rune_a pinned its surface.
        runner.register_spell(
            SpellDefinition(name="b", description=""), rune_name="rune_b"
        )
        assert set(runner.get_active_spells()) == {"a", "b"}

    def test_multiple_runes_set_active_spells_compose(self) -> None:
        runner = RuneRunner()
        runner.register_spell(
            SpellDefinition(name="a1", description=""), rune_name="rune_a"
        )
        runner.register_spell(
            SpellDefinition(name="a2", description=""), rune_name="rune_a"
        )
        runner.register_spell(
            SpellDefinition(name="b1", description=""), rune_name="rune_b"
        )
        runner.set_active_spells(["a1"], rune_name="rune_a")
        runner.set_active_spells(["b1"], rune_name="rune_b")
        # Each rune's set_active_spells only affects its own contribution, so
        # the effective set is the union rather than a clobbered global.
        assert set(runner.get_active_spells()) == {"a1", "b1"}

    def test_per_rune_pin_isolates_freeze(self) -> None:
        runner = RuneRunner()
        runner.register_spell(
            SpellDefinition(name="a", description=""), rune_name="rune_a"
        )
        runner.register_spell(
            SpellDefinition(name="b", description=""), rune_name="rune_b"
        )
        # rune_a narrows its own surface to {a} and pins it.
        runner.set_active_spells(["a"], rune_name="rune_a")
        # A later registration to rune_a stays out (pinned for rune_a only).
        runner.register_spell(
            SpellDefinition(name="a_extra", description=""), rune_name="rune_a"
        )
        # A registration to rune_b still joins the active set.
        runner.register_spell(
            SpellDefinition(name="b_extra", description=""), rune_name="rune_b"
        )
        active = set(runner.get_active_spells())
        assert "a" in active
        assert "b" in active
        assert "a_extra" not in active
        assert "b_extra" in active

    def test_rune_narrows_own_surface_only(self) -> None:
        runner = RuneRunner()
        runner.register_spell(
            SpellDefinition(name="a", description=""), rune_name="rune_a"
        )
        runner.register_spell(
            SpellDefinition(name="bash", description=""), rune_name="rune_a"
        )
        runner.register_spell(
            SpellDefinition(name="b", description=""), rune_name="rune_b"
        )
        # rune_a hides its own `bash` by pinning to {a}; rune_b's `b` is unaffected.
        runner.set_active_spells(["a"], rune_name="rune_a")
        active = set(runner.get_active_spells())
        assert active == {"a", "b"}

    def test_rune_can_widen_after_pinning_own_set(self) -> None:
        runner = RuneRunner()
        runner.register_spell(
            SpellDefinition(name="tool_search", description=""),
            rune_name="seeker",
        )
        runner.set_active_spells(["tool_search"], rune_name="seeker")
        # A rune may widen its own surface at runtime with a discovered name.
        runner.set_active_spells(["tool_search", "grep"], rune_name="seeker")
        assert set(runner.get_active_spells()) == {"tool_search", "grep"}

    def test_override_spell_migrates_active_set(self) -> None:
        runner = RuneRunner()
        runner.register_spell(
            SpellDefinition(name="shared", description="from A"),
            rune_name="rune_a",
        )
        assert runner.get_active_spells() == ["shared"]
        runner.register_spell(
            SpellDefinition(name="shared", description="from B"),
            rune_name="rune_b",
            override=True,
        )
        # rune_b now owns the spell in its active set
        # If rune_b narrows its set, rune_a's set does not keep the overridden spell
        runner.set_active_spells([], rune_name="rune_b")
        assert runner.get_active_spells() == []


class TestRuneRunnerGlobalAllowlist:
    def test_default_allowlist_is_none(self) -> None:
        runner = RuneRunner()
        assert runner.get_global_spell_allowlist() is None

    def test_set_allowlist(self) -> None:
        runner = RuneRunner()
        runner.set_global_spell_allowlist(["tool_search", "skill_search"])
        assert runner.get_global_spell_allowlist() == ["tool_search", "skill_search"]

    def test_set_allowlist_none_disables(self) -> None:
        runner = RuneRunner()
        runner.set_global_spell_allowlist(["tool_search"])
        runner.set_global_spell_allowlist(None)
        assert runner.get_global_spell_allowlist() is None

    def test_set_allowlist_copies_list(self) -> None:
        runner = RuneRunner()
        names = ["tool_search"]
        runner.set_global_spell_allowlist(names)
        names.append("bash")
        assert runner.get_global_spell_allowlist() == ["tool_search"]

    def test_widen_creates_when_none(self) -> None:
        runner = RuneRunner()
        runner.widen_global_allowlist(["tool_search"])
        assert runner.get_global_spell_allowlist() == ["tool_search"]

    def test_widen_merges_existing(self) -> None:
        runner = RuneRunner()
        runner.set_global_spell_allowlist(["tool_search", "skill_search"])
        runner.widen_global_allowlist(["grep"])
        assert set(runner.get_global_spell_allowlist()) == {
            "tool_search",
            "skill_search",
            "grep",
        }

    def test_widen_dedupes(self) -> None:
        runner = RuneRunner()
        runner.set_global_spell_allowlist(["tool_search"])
        runner.widen_global_allowlist(["tool_search", "grep"])
        result = runner.get_global_spell_allowlist()
        assert result.count("tool_search") == 1
        assert "grep" in result

    def test_allowlist_changes_increment_spell_version(self) -> None:
        runner = RuneRunner()
        initial = runner.spell_version
        runner.set_global_spell_allowlist(["tool_search"])
        assert runner.spell_version == initial + 1
        before_widen = runner.spell_version
        runner.widen_global_allowlist(["grep"])
        assert runner.spell_version == before_widen + 1
        before_disable = runner.spell_version
        runner.set_global_spell_allowlist(None)
        assert runner.spell_version == before_disable + 1


class TestRuneRunnerCommands:
    def test_register_and_get_commands(self) -> None:
        runner = RuneRunner()

        def handler() -> None:
            return None

        cmd = RegisteredCommand(
            name="test_cmd", description="A command", handler=handler
        )
        assert runner.register_command(cmd) is True
        commands = runner.get_commands()
        assert len(commands) == 1
        assert commands[0].name == "test_cmd"

    def test_first_command_wins(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        assert (
            runner.register_command(RegisteredCommand(name="dup", description="first"))
            is True
        )
        assert (
            runner.register_command(RegisteredCommand(name="dup", description="second"))
            is False
        )
        assert len(runner.get_commands()) == 1
        assert runner.get_commands()[0].description == "first"
        assert "Duplicate command registration skipped: dup" in caplog.text

    def test_override_command(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        assert (
            runner.register_command(RegisteredCommand(name="dup", description="first"))
            is True
        )
        with caplog.at_level(logging.DEBUG):
            assert (
                runner.register_command(
                    RegisteredCommand(name="dup", description="second"),
                    override=True,
                )
                is True
            )
        assert len(runner.get_commands()) == 1
        assert runner.get_commands()[0].description == "second"
        assert "Overwriting existing command registration" in caplog.text
        assert "Duplicate command registration skipped" not in caplog.text


class TestRuneRunnerShortcuts:
    def test_register_and_get_shortcuts(self) -> None:
        runner = RuneRunner()
        shortcut = RuneShortcut(key="ctrl+k", description="Test", handler=lambda: None)
        assert runner.register_shortcut(shortcut) is True
        shortcuts = runner.get_shortcuts()
        assert len(shortcuts) == 1
        assert shortcuts[0].key == "ctrl+k"

    def test_duplicate_shortcut_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        runner = RuneRunner()
        shortcut1 = RuneShortcut(
            key="ctrl+k", description="First", handler=lambda: None
        )
        shortcut2 = RuneShortcut(
            key="ctrl+k", description="Second", handler=lambda: None
        )
        assert runner.register_shortcut(shortcut1) is True
        assert runner.register_shortcut(shortcut2) is False
        assert len(runner.get_shortcuts()) == 1
        assert "Duplicate shortcut registration skipped" in caplog.text

    def test_override_shortcut(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        shortcut1 = RuneShortcut(
            key="ctrl+k", description="First", handler=lambda: None
        )
        shortcut2 = RuneShortcut(
            key="ctrl+k", description="Second", handler=lambda: None
        )
        assert runner.register_shortcut(shortcut1) is True
        with caplog.at_level(logging.DEBUG):
            assert runner.register_shortcut(shortcut2, override=True) is True
        assert len(runner.get_shortcuts()) == 1
        assert runner.get_shortcuts()[0].description == "Second"
        assert "Overwriting existing shortcut registration" in caplog.text
        assert "Duplicate shortcut registration skipped" not in caplog.text


class TestRuneRunnerProviders:
    def test_register_provider(self) -> None:
        runner = RuneRunner()
        assert runner.register_provider("test", {"api_key": "xyz"}) is True
        assert runner.get_registered_providers()["test"] == {"api_key": "xyz"}

    def test_first_provider_wins(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        assert runner.register_provider("test", {"api_key": "first"}) is True
        assert runner.register_provider("test", {"api_key": "second"}) is False
        assert runner.get_registered_providers()["test"]["api_key"] == "first"
        assert "Duplicate provider registration skipped: test" in caplog.text

    def test_override_provider(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = RuneRunner()
        assert runner.register_provider("test", {"api_key": "first"}) is True
        with caplog.at_level(logging.DEBUG):
            assert (
                runner.register_provider("test", {"api_key": "second"}, override=True)
                is True
            )
        assert runner.get_registered_providers()["test"]["api_key"] == "second"
        assert "Overwriting existing provider registration" in caplog.text
        assert "Duplicate provider registration skipped" not in caplog.text

    def test_get_registered_providers(self) -> None:
        runner = RuneRunner()
        assert runner.get_registered_providers() == {}
        assert runner.register_provider("a", {"key": 1}) is True
        assert runner.register_provider("b", {"key": 2}) is True
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
    async def test_load_rune_loads_calls_factories(self) -> None:
        runner = RuneRunner()
        called = False

        def factory(api):
            nonlocal called
            called = True

        manifest = RuneManifest(name="test", version="1.0.0", description="Test")
        await runner.load_rune_loads([RuneLoad(manifest=manifest, factory=factory)])
        assert called

    @pytest.mark.asyncio
    async def test_load_rune_loads_async_factory(self) -> None:
        runner = RuneRunner()
        called = False

        async def factory(api):
            nonlocal called
            called = True

        manifest = RuneManifest(name="test", version="1.0.0", description="Test")
        await runner.load_rune_loads([RuneLoad(manifest=manifest, factory=factory)])
        assert called

    @pytest.mark.asyncio
    async def test_load_rune_loads_registers_spells(self) -> None:
        runner = RuneRunner()

        def factory(api):
            api.register_spell(
                SpellDefinition(name="rune_spell", description="From rune")
            )

        manifest = RuneManifest(name="test", version="1.0.0", description="Test")
        await runner.load_rune_loads([RuneLoad(manifest=manifest, factory=factory)])
        assert len(runner.get_all_registered_spells()) == 1
        assert runner.get_all_registered_spells()[0].name == "rune_spell"

    @pytest.mark.asyncio
    async def test_load_rune_loads_registers_hooks(self) -> None:
        runner = RuneRunner()

        def factory(api):
            api.on(SigilHook.TURN_START, lambda d: None)

        manifest = RuneManifest(name="test", version="1.0.0", description="Test")
        await runner.load_rune_loads([RuneLoad(manifest=manifest, factory=factory)])
        assert len(runner.get_sigil_handlers(SigilHook.TURN_START)) == 1

    @pytest.mark.asyncio
    async def test_load_rune_loads_registers_manifest_shortcuts(self) -> None:
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

        await runner.load_rune_loads([RuneLoad(manifest=manifest, factory=factory)])
        shortcuts = runner.get_shortcuts()
        assert len(shortcuts) == 2
        assert shortcuts[0].key == "ctrl+k"
        assert shortcuts[1].key == "ctrl+r"


class TestRuneRunnerProvenance:
    @pytest.mark.asyncio
    async def test_spell_provenance_set_from_loading_rune(self) -> None:
        runner = RuneRunner()
        manifest = RuneManifest(
            name="my_rune",
            version="1.0.0",
            description="Test",
            scope=RuneScope.USER,
            path="/tmp/my_rune",
        )

        def factory(api: Any) -> None:
            api.register_spell(
                SpellDefinition(name="rune_spell", description="From rune")
            )

        load = RuneLoad(manifest=manifest, factory=factory)
        await runner.load_rune_loads([load])
        spells = runner.get_all_registered_spells()
        assert len(spells) == 1
        assert spells[0].source_rune == "my_rune"

    @pytest.mark.asyncio
    async def test_spell_provenance_none_without_rune(self) -> None:
        runner = RuneRunner()
        spell = SpellDefinition(name="builtin_spell", description="Builtin")
        runner.register_spell(spell)
        assert spell.source_rune is None

    @pytest.mark.asyncio
    async def test_loaded_manifests_retained(self) -> None:
        runner = RuneRunner()
        manifest = RuneManifest(
            name="retained_rune",
            version="1.0.0",
            description="Test",
            scope=RuneScope.PROJECT,
            path="/tmp/retained",
        )

        def factory(api: Any) -> None:
            pass

        load = RuneLoad(manifest=manifest, factory=factory)
        await runner.load_rune_loads([load])
        assert len(runner.loaded_manifests) == 1
        assert runner.loaded_manifests[0].name == "retained_rune"
        assert runner.loaded_manifests[0].scope == RuneScope.PROJECT
        assert runner.loaded_manifests[0].path == "/tmp/retained"

    @pytest.mark.asyncio
    async def test_manifest_scope_recorded(self) -> None:
        runner = RuneRunner()
        manifest = RuneManifest(
            name="scoped_rune",
            version="1.0.0",
            description="Test",
            scope=RuneScope.AGENT,
            path="/tmp/scoped",
        )

        def factory(api: Any) -> None:
            pass

        load = RuneLoad(manifest=manifest, factory=factory)
        await runner.load_rune_loads([load])
        assert runner.loaded_manifests[0].scope == RuneScope.AGENT


class TestRuneRunnerDedup:
    @pytest.mark.asyncio
    async def test_duplicate_rune_skips_factory(self) -> None:
        runner = RuneRunner()
        call_count = 0

        def factory(api: Any) -> None:
            nonlocal call_count
            call_count += 1

        manifest1 = RuneManifest(
            name="dup_rune",
            version="1.0.0",
            description="First",
            scope=RuneScope.PROJECT,
            path="/tmp/first",
        )
        manifest2 = RuneManifest(
            name="dup_rune",
            version="2.0.0",
            description="Second",
            scope=RuneScope.USER,
            path="/tmp/second",
        )
        loads = [
            RuneLoad(manifest=manifest1, factory=factory),
            RuneLoad(manifest=manifest2, factory=factory),
        ]
        await runner.load_rune_loads(loads)
        assert call_count == 1
        assert len(runner.loaded_manifests) == 1
        assert runner.loaded_manifests[0].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_duplicate_rune_no_double_sigil_registration(self) -> None:
        runner = RuneRunner()
        handler = MagicMock()

        def factory(api: Any) -> None:
            api.on(SigilHook.TURN_START, handler)

        manifest1 = RuneManifest(
            name="sigil_rune",
            version="1.0.0",
            description="First",
            scope=RuneScope.PROJECT,
            path="/tmp/first",
        )
        manifest2 = RuneManifest(
            name="sigil_rune",
            version="2.0.0",
            description="Second",
            scope=RuneScope.USER,
            path="/tmp/second",
        )
        loads = [
            RuneLoad(manifest=manifest1, factory=factory),
            RuneLoad(manifest=manifest2, factory=factory),
        ]
        await runner.load_rune_loads(loads)
        assert len(runner.get_sigil_handlers(SigilHook.TURN_START)) == 1


class TestRuneRunnerSkills:
    def test_load_skills(self) -> None:
        runner = RuneRunner()
        skill1 = SkillManifest(
            name="skill-one",
            description="First skill",
            scope=SkillScope.PROJECT,
            path="/tmp/skill-one",
        )
        skill2 = SkillManifest(
            name="skill-two",
            description="Second skill",
            scope=SkillScope.USER,
            path="/tmp/skill-two",
        )
        loads = [SkillLoad(manifest=skill1), SkillLoad(manifest=skill2)]
        runner.load_skills(loads)

        skills = runner.get_skills()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"skill-one", "skill-two"}

    def test_get_skills_empty(self) -> None:
        runner = RuneRunner()
        assert runner.get_skills() == []

    def test_get_skill_catalog(self) -> None:
        runner = RuneRunner()
        skill1 = SkillManifest(
            name="skill-one",
            description="First skill",
            scope=SkillScope.PROJECT,
            path="/tmp/skill-one",
            version="1.0.0",
        )
        skill2 = SkillManifest(
            name="skill-two",
            description="Second skill",
            scope=SkillScope.USER,
            path="/tmp/skill-two",
        )
        runner.load_skills([SkillLoad(manifest=skill1), SkillLoad(manifest=skill2)])

        catalog = runner.get_skill_catalog()
        assert "## Available Skills" in catalog
        assert "skill-one" in catalog
        assert "First skill" in catalog
        assert "project" in catalog
        assert "/tmp/skill-one" in catalog
        assert "1.0.0" in catalog
        assert "skill-two" in catalog
        assert "Second skill" in catalog
        assert "user" in catalog
        assert "/tmp/skill-two" in catalog

    def test_load_skills_stores_diagnostics(self) -> None:
        runner = RuneRunner()
        skill = SkillManifest(
            name="loaded-skill",
            description="Loaded",
            scope=SkillScope.PROJECT,
            path="/tmp/loaded",
        )
        diag = SkillDiagnostic(
            kind=SkillDiagnosticKind.SHADOWED_SKILL,
            skill_name="dup-skill",
            message="shadowed",
            scope=SkillScope.USER,
            path="/tmp/dup",
        )
        runner.load_skills([SkillLoad(manifest=skill)], diagnostics=[diag])

        assert runner.skill_diagnostics == [diag]

    def test_skill_diagnostics_empty_by_default(self) -> None:
        runner = RuneRunner()
        assert runner.skill_diagnostics == []

    def test_load_skills_without_diagnostics_still_works(self) -> None:
        runner = RuneRunner()
        skill = SkillManifest(
            name="no-diag", description="d", scope=SkillScope.PROJECT, path="/x"
        )
        runner.load_skills([SkillLoad(manifest=skill)])
        assert runner.skill_diagnostics == []
        assert len(runner.get_skills()) == 1

    def test_load_skills_diagnostics_accumulate(self) -> None:
        runner = RuneRunner()
        diag1 = SkillDiagnostic(
            kind=SkillDiagnosticKind.PARSE_WARNING,
            skill_name="s1",
            message="bad",
        )
        diag2 = SkillDiagnostic(
            kind=SkillDiagnosticKind.SHADOWED_SKILL,
            skill_name="s2",
            message="dup",
        )
        runner.load_skills([], diagnostics=[diag1])
        runner.load_skills([], diagnostics=[diag2])
        assert runner.skill_diagnostics == [diag1, diag2]

    def test_extend_diagnostics_appends(self) -> None:
        runner = RuneRunner()
        diag = Diagnostic(
            kind=DiagnosticKind.PARSE_WARNING,
            rune_name="r1",
            message="warned",
        )
        runner.extend_diagnostics([diag])
        assert runner.diagnostics == [diag]

    def test_extend_skill_diagnostics_appends(self) -> None:
        runner = RuneRunner()
        sdiag = SkillDiagnostic(
            kind=SkillDiagnosticKind.PARSE_WARNING,
            skill_name="s1",
            message="warned",
        )
        runner.extend_skill_diagnostics([sdiag])
        assert runner.skill_diagnostics == [sdiag]

    def test_get_skill_catalog_empty(self) -> None:
        runner = RuneRunner()
        assert runner.get_skill_catalog() == ""

    def test_suppress_skill_catalog(self) -> None:
        runner = RuneRunner()
        skill = SkillManifest(
            name="test-skill",
            description="Test skill",
            scope=SkillScope.PROJECT,
            path="/tmp/test",
        )
        runner.load_skills([SkillLoad(manifest=skill)])

        # By default, not suppressed
        assert not runner.is_skill_catalog_suppressed()
        assert runner.get_skill_catalog() != ""

        # Suppress it
        runner.suppress_skill_catalog(True)
        assert runner.is_skill_catalog_suppressed()
        assert runner.get_skill_catalog() == ""

        # Unsuppress it
        runner.suppress_skill_catalog(False)
        assert not runner.is_skill_catalog_suppressed()
        assert runner.get_skill_catalog() != ""


class TestRuneRunnerSigils:
    def test_register_and_get_handlers(self) -> None:
        runner = RuneRunner()

        def sync_handler() -> None:
            pass

        async def async_handler() -> None:
            pass

        runner.register_handler(SigilHook.BEFORE_INVOCATION, sync_handler)
        runner.register_handler(SigilHook.BEFORE_INVOCATION, async_handler)

        handlers = runner.get_sigil_handlers(SigilHook.BEFORE_INVOCATION)
        assert len(handlers) == 2
        assert sync_handler in handlers
        assert async_handler in handlers

    def test_get_handlers_empty(self) -> None:
        runner = RuneRunner()
        handlers = runner.get_sigil_handlers(SigilHook.BEFORE_INVOCATION)
        assert handlers == []

    def test_sigil_handlers_property(self) -> None:
        runner = RuneRunner()
        runner.register_handler(SigilHook.BEFORE_INVOCATION, lambda: None)
        runner.register_handler(SigilHook.AFTER_INVOCATION, lambda: None)

        handlers = runner.sigil_handlers
        assert isinstance(handlers, dict)
        assert SigilHook.BEFORE_INVOCATION in handlers
        assert SigilHook.AFTER_INVOCATION in handlers
        assert len(handlers[SigilHook.BEFORE_INVOCATION]) == 1
        assert len(handlers[SigilHook.AFTER_INVOCATION]) == 1


class TestRuneRunnerContext:
    def test_default_runner_context(self) -> None:
        runner = RuneRunner()
        assert runner.context == RuneContext()

    def test_bind_context(self) -> None:
        runner = RuneRunner()
        ctx = RuneContext(
            cwd="/workspace",
            mode="cli",
            has_ui=False,
            agent_name="tester",
            api_key="key-123",
        )
        runner.bind_context(ctx)
        assert runner.context == ctx
        assert runner.context.agent_name == "tester"
        assert runner.context.api_key == "key-123"


class TestRealmFactoryRegistration:
    def test_register_and_get_realm_factory(self) -> None:
        runner = RuneRunner()

        def factory(**kwargs: Any) -> None:
            return None

        assert runner.register_realm_factory(
            "test_provider", factory, rune_name="test_rune"
        )
        factories = runner.get_registered_realm_factories()
        assert "test_provider" in factories
        assert factories["test_provider"] is factory

    def test_duplicate_registration_without_override(self) -> None:
        runner = RuneRunner()

        def f1(**kwargs: Any) -> int:
            return 1

        def f2(**kwargs: Any) -> int:
            return 2

        assert runner.register_realm_factory("p", f1)
        assert not runner.register_realm_factory("p", f2, override=False)
        assert runner.get_registered_realm_factories()["p"] is f1
        assert runner.register_realm_factory("p", f2, override=True)
        assert runner.get_registered_realm_factories()["p"] is f2

    def test_clear_rune_evicts_realm_factories(self) -> None:
        runner = RuneRunner()

        def f1(**kwargs: Any) -> int:
            return 1

        def f2(**kwargs: Any) -> int:
            return 2

        runner.register_realm_factory("p1", f1, rune_name="rune_a")
        runner.register_realm_factory("p2", f2, rune_name="rune_b")
        assert len(runner.get_registered_realm_factories()) == 2
        runner.clear_rune("rune_a")
        factories = runner.get_registered_realm_factories()
        assert "p1" not in factories
        assert "p2" in factories
