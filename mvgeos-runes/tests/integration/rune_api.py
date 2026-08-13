from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mvgeos_agent import MvgeSandbox

from mvgeos_runes.rune_api import RuneAPI
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    SigilHook,
    SpellDefinition,
)


@pytest.fixture
def runner() -> RuneRunner:
    return RuneRunner()


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
        assert handler in runner._sigils.get_handlers(SigilHook.TURN_START)

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
    def test_sandbox_property_returns_mvge_sandbox(
        self, api: RuneAPI, runner: RuneRunner
    ) -> None:
        sandbox = api.sandbox
        assert isinstance(sandbox, MvgeSandbox)
        assert sandbox is runner.sandbox

    def test_sandbox_execute_code_works(self, api: RuneAPI) -> None:
        result = api.sandbox.execute_code(
            "x = 1 + 2",
            allowed_modules=set(),
        )
        assert result == {"x": 3}
