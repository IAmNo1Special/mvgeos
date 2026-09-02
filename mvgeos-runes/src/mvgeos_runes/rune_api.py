from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mvgeos_runes.rune_runner import RuneRunner

from mvgeos_runes.types import (
    RegisteredCommand,
    RuneShortcut,
    Sandbox,
    SigilHook,
    SkillManifest,
    SpellDefinition,
)

RuneFactory = Callable[["RuneAPI"], None | Awaitable[None]]


class RuneAPI:
    def __init__(self, runner: RuneRunner, rune_name: str | None = None) -> None:
        self._runner = runner
        self._rune_name = rune_name

    @property
    def sandbox(self) -> Sandbox:
        return self._runner.sandbox

    def on(self, hook: SigilHook, handler: Any) -> None:
        self._runner.register_handler(hook, handler)

    def register_spell(self, spell: SpellDefinition, override: bool = False) -> bool:
        return self._runner.register_spell(spell, self._rune_name, override=override)

    def register_command(
        self,
        name: str,
        description: str = "",
        handler: Any = None,
        override: bool = False,
    ) -> bool:
        return self._runner.register_command(
            RegisteredCommand(name=name, description=description, handler=handler),
            override=override,
        )

    def register_shortcut(
        self,
        key: str,
        description: str = "",
        handler: Any = None,
        override: bool = False,
    ) -> bool:
        return self._runner.register_shortcut(
            RuneShortcut(key=key, description=description, handler=handler),
            override=override,
        )

    def register_provider(
        self,
        name: str,
        config: dict[str, Any],
        override: bool = False,
    ) -> bool:
        return self._runner.register_provider(name, config, override=override)

    def get_registered_providers(
        self,
    ) -> dict[str, dict[str, Any]]:
        return self._runner.get_registered_providers()

    def get_active_spells(self) -> list[str]:
        return self._runner.get_active_spells()

    def set_active_spells(self, spell_names: list[str]) -> None:
        self._runner.set_active_spells(spell_names, self._rune_name)

    def get_all_spells(self) -> list[SpellDefinition]:
        return self._runner.get_all_registered_spells()

    def get_shortcuts(self) -> list[RuneShortcut]:
        return self._runner.get_shortcuts()

    def get_skills(self) -> list[SkillManifest]:
        """Get all registered skills."""
        return self._runner.get_skills()

    def get_skill_catalog(self) -> str:
        """Get the skill catalog formatted for system prompt injection."""
        return self._runner.get_skill_catalog()

    def send_message(self, content: str) -> None:
        self._runner.send_message(content)

    def set_session_name(self, name: str) -> None:
        self._runner.set_session_name(name)

    def on_event(self, channel: str, handler: Any) -> None:
        self._runner.on_event(channel, handler)

    def emit_event(self, channel: str, data: Any) -> None:
        self._runner.emit_event(channel, data)
