from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any

from mvgeos_agent import MvgeSandbox

from mvgeos_runes.rune_api import RuneAPI, RuneFactory
from mvgeos_runes.sigils import SigilRegistry
from mvgeos_runes.types import (
    Diagnostic,
    RegisteredCommand,
    RuneContext,
    RuneLoad,
    RuneManifest,
    RuneShortcut,
    SigilHook,
    SpellDefinition,
)

logger = logging.getLogger(__name__)


def _call_handler(handler: Any, hook: SigilHook, data: Any) -> Any:
    if callable(handler):
        return handler(data)
    attr = getattr(handler, hook.value, None)
    if attr is not None:
        return attr(data)
    return None


async def _call_handler_async(handler: Any, hook: SigilHook, data: Any) -> Any:
    result = _call_handler(handler, hook, data)
    if isinstance(result, Awaitable):
        result = await result
    return result


async def _safe_call_handler_async(
    handler: Any, hook: SigilHook, data: Any
) -> Any | None:
    return await _call_handler_async(handler, hook, data)


class RuneRunner:
    def __init__(self) -> None:
        self._sigils = SigilRegistry()
        self._spells: dict[str, SpellDefinition] = {}
        self._commands: dict[str, RegisteredCommand] = {}
        self._shortcuts: dict[str, RuneShortcut] = {}
        self._providers: dict[str, dict[str, Any]] = {}
        self._context = RuneContext()
        self._message_queue: list[str] = []
        self._session_name: str | None = None
        self._event_handlers: dict[str, list[Any]] = {}
        self._sandbox = MvgeSandbox()
        self._loaded_manifests: list[RuneManifest] = []
        self._diagnostics: list[Diagnostic] = []
        self._loaded_rune_names: set[str] = set()
        self._current_loading_rune: str | None = None

    @property
    def context(self) -> RuneContext:
        return self._context

    @property
    def sandbox(self) -> MvgeSandbox:
        return self._sandbox

    @property
    def loaded_manifests(self) -> list[RuneManifest]:
        return list(self._loaded_manifests)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return list(self._diagnostics)

    def bind_context(self, context: RuneContext) -> None:
        self._context = context

    def register_handler(self, hook: SigilHook, handler: Any) -> None:
        self._sigils.register(hook, handler)

    def register_spell(self, spell: SpellDefinition) -> None:
        if spell.name not in self._spells:
            if spell.source_rune is None and self._current_loading_rune is not None:
                spell.source_rune = self._current_loading_rune
            self._spells[spell.name] = spell
        else:
            logger.warning("Duplicate spell registration skipped: %s", spell.name)

    def register_command(self, command: RegisteredCommand) -> None:
        if command.name not in self._commands:
            self._commands[command.name] = command
        else:
            logger.warning("Duplicate command registration skipped: %s", command.name)

    def register_shortcut(self, shortcut: RuneShortcut) -> None:
        if shortcut.key not in self._shortcuts:
            self._shortcuts[shortcut.key] = shortcut
        else:
            logger.warning("Duplicate shortcut registration skipped: %s", shortcut.key)

    def register_provider(self, name: str, config: dict[str, Any]) -> None:
        if name not in self._providers:
            self._providers[name] = config
        else:
            logger.warning("Duplicate provider registration skipped: %s", name)

    def get_registered_providers(self) -> dict[str, dict[str, Any]]:
        return dict(self._providers)

    def get_all_registered_spells(self) -> list[SpellDefinition]:
        return list(self._spells.values())

    def get_commands(self) -> list[RegisteredCommand]:
        return list(self._commands.values())

    def get_shortcuts(self) -> list[RuneShortcut]:
        return list(self._shortcuts.values())

    def get_active_spells(self) -> list[str]:
        return list(self._spells.keys())

    def send_message(self, content: str) -> None:
        self._message_queue.append(content)

    def set_session_name(self, name: str) -> None:
        self._session_name = name

    def create_api(self) -> RuneAPI:
        return RuneAPI(self)

    async def load_runes(
        self,
        factories: list[RuneFactory],
        manifests: list[RuneManifest] | None = None,
    ) -> None:
        for manifest in manifests or []:
            if manifest.name not in self._loaded_rune_names:
                self._loaded_manifests.append(manifest)
                self._loaded_rune_names.add(manifest.name)
            for sc in manifest.shortcuts:
                self.register_shortcut(sc)
        for factory in factories:
            api = self.create_api()
            result = factory(api)
            if isinstance(result, Awaitable):
                await result

    async def load_rune_loads(
        self,
        loads: list[RuneLoad],
        diagnostics: list[Diagnostic] | None = None,
    ) -> None:
        if diagnostics is not None:
            self._diagnostics.extend(diagnostics)
        for load in loads:
            if load.manifest.name not in self._loaded_rune_names:
                self._loaded_manifests.append(load.manifest)
                self._loaded_rune_names.add(load.manifest.name)
            else:
                continue
            for sc in load.manifest.shortcuts:
                self.register_shortcut(sc)
            if load.factory is not None:
                self._current_loading_rune = load.manifest.name
                api = self.create_api()
                result = load.factory(api)
                if isinstance(result, Awaitable):
                    await result
                self._current_loading_rune = None

    async def emit_async(self, hook: SigilHook, data: Any) -> None:
        for handler in self._sigils.get_handlers(hook):
            await _safe_call_handler_async(handler, hook, data)

    async def emit_chain(self, hook: SigilHook, initial: Any) -> Any:
        current = initial
        for handler in self._sigils.get_handlers(hook):
            result = await _safe_call_handler_async(handler, hook, current)
            if result is not None:
                current = result
        return current

    async def emit_first(self, hook: SigilHook, data: Any) -> Any | None:
        for handler in self._sigils.get_handlers(hook):
            result = await _safe_call_handler_async(handler, hook, data)
            if result is not None:
                return result
        return None

    async def emit_block(self, hook: SigilHook, data: Any) -> dict[str, Any] | None:
        for handler in self._sigils.get_handlers(hook):
            result = await _safe_call_handler_async(handler, hook, data)
            if isinstance(result, dict) and result.get("block"):
                return result
        return None

    def on_event(self, channel: str, handler: Any) -> None:
        if channel not in self._event_handlers:
            self._event_handlers[channel] = []
        self._event_handlers[channel].append(handler)

    def emit_event(self, channel: str, data: Any) -> None:
        for handler in self._event_handlers.get(channel, []):
            try:
                handler(data)
            except Exception:
                logger.exception(
                    "Event handler for channel %s raised an exception", channel
                )

    def get_event_channels(self) -> list[str]:
        return list(self._event_handlers.keys())
