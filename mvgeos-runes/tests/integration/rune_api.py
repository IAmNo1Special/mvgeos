from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mvgeos_runes.rune_api import RuneAPI
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Sandbox,
    SigilHook,
    SpellDefinition,
)


class StubSandbox:
    """Sandbox test double satisfying the runes Sandbox protocol."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, set[str] | None]] = []

    def execute_code(
        self,
        code_str: str,
        context_globals: dict[str, Any] | None = None,
        timeout_seconds: float = 5.0,
        allowed_modules: set[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((code_str, allowed_modules))
        return {"x": 3}


@pytest.fixture
def sandbox() -> StubSandbox:
    return StubSandbox()


@pytest.fixture
def runner(sandbox: StubSandbox) -> RuneRunner:
    return RuneRunner(sandbox_factory=lambda: sandbox)


@pytest.fixture
def api(runner: RuneRunner) -> RuneAPI:
    return runner.create_api()


class TestRuneAPIRegistration:
    def test_register_spell_delegates_to_runner(
        self, api: RuneAPI, runner: RuneRunner
    ) -> None:
        spell = SpellDefinition(name="test_spell", description="Test")
        api.register_spell(spell)
        assert runner.get_all_registered_spells() == [spell]

    def test_register_spell_first_wins(self, api: RuneAPI, runner: RuneRunner) -> None:
        api.register_spell(SpellDefinition(name="dup", description="first"))
        api.register_spell(SpellDefinition(name="dup", description="second"))
        assert len(runner.get_all_registered_spells()) == 1
        assert runner.get_all_registered_spells()[0].description == "first"

    def test_on_registers_handler(self, api: RuneAPI, runner: RuneRunner) -> None:
        def handler(data: dict) -> None:
            return None

        api.on(SigilHook.TURN_START, handler)
        assert handler in runner.get_sigil_handlers(SigilHook.TURN_START)

    def test_get_all_spells(self, api: RuneAPI, runner: RuneRunner) -> None:
        spell = SpellDefinition(name="s1", description="")
        api.register_spell(spell)
        assert api.get_all_spells() == [spell]

    def test_get_active_spells(self, api: RuneAPI, runner: RuneRunner) -> None:
        api.register_spell(SpellDefinition(name="a", description=""))
        api.register_spell(SpellDefinition(name="b", description=""))
        assert api.get_active_spells() == ["a", "b"]

    def test_set_active_spells_delegates_to_runner(
        self, api: RuneAPI, runner: RuneRunner
    ) -> None:
        api.register_spell(SpellDefinition(name="tool_search", description=""))
        api.register_spell(SpellDefinition(name="bash", description=""))
        api.set_active_spells(["tool_search"])
        assert runner.get_active_spells() == ["tool_search"]

    def test_register_command(self, api: RuneAPI, runner: RuneRunner) -> None:
        def handler() -> None:
            return None

        api.register_command("my_cmd", description="A command", handler=handler)
        cmds = runner.get_commands()
        assert len(cmds) == 1
        assert cmds[0].name == "my_cmd"
        assert cmds[0].handler is handler

    def test_register_shortcut(self, api: RuneAPI, runner: RuneRunner) -> None:
        def handler() -> None:
            return None

        api.register_shortcut("ctrl+k", description="Test", handler=handler)
        shortcuts = runner.get_shortcuts()
        assert len(shortcuts) == 1
        assert shortcuts[0].key == "ctrl+k"

    def test_get_shortcuts(self, api: RuneAPI, runner: RuneRunner) -> None:
        api.register_shortcut("ctrl+k", description="Test")
        api.register_shortcut("ctrl+r", description="Reload")
        result = api.get_shortcuts()
        assert len(result) == 2
        assert result[0].key == "ctrl+k"
        assert result[1].key == "ctrl+r"

    def test_register_provider(self, api: RuneAPI, runner: RuneRunner) -> None:
        api.register_provider("custom", {"api_key": "sekret"})
        assert runner._providers["custom"] == {"api_key": "sekret"}

    def test_send_message(self, api: RuneAPI, runner: RuneRunner) -> None:
        api.send_message("hello from rune")
        assert runner._message_queue == ["hello from rune"]

    def test_set_session_name(self, api: RuneAPI, runner: RuneRunner) -> None:
        api.set_session_name("rune-session")
        assert runner._session_name == "rune-session"


class TestRuneAPIActiveSpells:
    def test_api_scoped_to_rune_name(self, runner: RuneRunner) -> None:
        api_a = runner.create_api(rune_name="rune_a")
        api_b = runner.create_api(rune_name="rune_b")
        api_a.register_spell(SpellDefinition(name="a", description=""))
        api_b.register_spell(SpellDefinition(name="b", description=""))
        # rune_a narrows its own surface; rune_b is unaffected.
        api_a.set_active_spells(["a"])
        assert set(runner.get_active_spells()) == {"a", "b"}

    def test_two_apis_compose_active_sets(self, runner: RuneRunner) -> None:
        api_a = runner.create_api(rune_name="rune_a")
        api_b = runner.create_api(rune_name="rune_b")
        api_a.register_spell(SpellDefinition(name="a1", description=""))
        api_a.register_spell(SpellDefinition(name="a2", description=""))
        api_b.register_spell(SpellDefinition(name="b1", description=""))
        api_a.set_active_spells(["a1"])
        api_b.set_active_spells(["b1"])
        assert set(runner.get_active_spells()) == {"a1", "b1"}


class TestRuneAPIEventBus:
    def test_on_event_delegates_to_runner(
        self, api: RuneAPI, runner: RuneRunner
    ) -> None:
        handler = MagicMock()
        api.on_event("custom:ch", handler)
        assert "custom:ch" in runner.get_event_channels()

    def test_emit_event_delegates_to_runner(
        self, api: RuneAPI, runner: RuneRunner
    ) -> None:
        handler = MagicMock()
        api.on_event("custom:ch", handler)
        api.emit_event("custom:ch", {"data": 1})
        handler.assert_called_once_with({"data": 1})


class TestRuneAPISandbox:
    def test_sandbox_property_returns_injected_sandbox(
        self, api: RuneAPI, runner: RuneRunner, sandbox: StubSandbox
    ) -> None:
        assert isinstance(api.sandbox, Sandbox)
        assert api.sandbox is sandbox
        assert api.sandbox is runner.sandbox

    def test_sandbox_execute_code_delegates(self, api: RuneAPI) -> None:
        result = api.sandbox.execute_code(
            "x = 1 + 2",
            allowed_modules=set(),
        )
        assert result == {"x": 3}

    def test_sandbox_without_factory_raises(self) -> None:
        runner = RuneRunner()
        with pytest.raises(RuntimeError, match="No sandbox configured"):
            _ = runner.sandbox
