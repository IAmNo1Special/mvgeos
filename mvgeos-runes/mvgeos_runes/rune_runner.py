from __future__ import annotations

import asyncio
import contextlib
import logging
import traceback
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mvgeos_agent.sandbox import MvgeSandbox

    from mvgeos_runes.rune_api import RuneAPI, RuneFactory
else:
    from mvgeos_runes.rune_api import RuneAPI, RuneFactory

from mvgeos_runes.sigils import SigilRegistry
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    RegisteredCommand,
    RuneContext,
    RuneLoad,
    RuneManifest,
    RuneShortcut,
    SigilHook,
    SkillDiagnostic,
    SkillLoad,
    SkillManifest,
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
    handler: Any,
    hook: SigilHook,
    data: Any,
    diagnostics: list[Diagnostic] | None = None,
) -> Any | None:
    try:
        return await _call_handler_async(handler, hook, data)
    except asyncio.CancelledError:
        raise
    except Exception as err:
        tb = traceback.format_exc()
        logger.warning(
            "Sigil handler for hook %s raised an exception: %s\n%s",
            hook.value,
            err,
            tb,
        )
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    kind=DiagnosticKind.LOAD_FAILURE,
                    rune_name=getattr(handler, "__name__", "sigil_handler"),
                    message=f"Sigil handler error on {hook.value}: {err}\n{tb}",
                )
            )
        raise


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
        self._sandbox: Any | None = None
        self._loaded_manifests: list[RuneManifest] = []
        self._diagnostics: list[Diagnostic] = []
        self._loaded_rune_names: set[str] = set()
        self._current_loading_rune: str | None = None
        self._loaded_skills: list[SkillLoad] = []
        self._skill_diagnostics: list[SkillDiagnostic] = []
        self._suppress_skill_catalog: bool = False
        # The effective active-spell set is the *union* of each rune's own
        # contribution: ``_active_spells_by_rune`` maps a rune name (or ``None``
        # for spells registered outside any rune context) to the set of spell
        # names it has declared active. A rune that calls ``set_active_spells``
        # only narrows/freezes its own entry; it never locks out other runes.
        self._active_spells_by_rune: dict[str | None, set[str]] = {}
        self._pinned_runes: set[str | None] = set()

    @property
    def context(self) -> RuneContext:
        return self._context

    @property
    def sandbox(self) -> MvgeSandbox:
        if self._sandbox is None:
            from mvgeos_agent.sandbox import MvgeSandbox

            self._sandbox = MvgeSandbox()
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

    def register_spell(
        self, spell: SpellDefinition, rune_name: str | None = None
    ) -> None:
        if rune_name is None:
            rune_name = self._current_loading_rune
        if spell.name not in self._spells:
            if getattr(spell, "source_rune", None) is None and rune_name is not None:
                with contextlib.suppress(AttributeError):
                    spell.source_rune = rune_name
            self._spells[spell.name] = spell
            # Seed the rune's own active set with every registered rune spell by
            # default, unless that rune has already pinned an explicit set. Other
            # runes' pinned sets are left untouched (composable per-rune model).
            if rune_name not in self._pinned_runes:
                self._active_spells_by_rune.setdefault(rune_name, set()).add(spell.name)
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
        active: set[str] = set()
        for rune_spells in self._active_spells_by_rune.values():
            active |= rune_spells
        return sorted(active)

    def set_active_spells(
        self, spell_names: list[str], rune_name: str | None = None
    ) -> None:
        """Declare the rune-owned active-spell set for a single rune.

        Unlike a global replace and freeze, this only sets the calling rune's own
        contribution; the engine's effective active set is the union across all
        runes (``get_active_spells``). A rune that wants to narrow its own
        surface does so without affecting other runes' spells.

        ``rune_name`` defaults to the rune currently being loaded so that
        factory-time calls (before sigils fire) are attributed correctly. When
        invoked through a ``RuneAPI`` tied to a rune, the rune name is carried
        on the API instance, surviving past the loading phase into
        ``SESSION_START`` handlers, so later spell registrations from other
        runes still join the unioned active set.
        """
        if rune_name is None:
            rune_name = self._current_loading_rune
        self._active_spells_by_rune[rune_name] = set(spell_names)
        self._pinned_runes.add(rune_name)

    def load_skills(
        self,
        loads: list[SkillLoad],
        diagnostics: list[SkillDiagnostic] | None = None,
    ) -> None:
        """Load skills from discovery.

        Args:
            loads: List of skill loads (manifests) from discovery.
            diagnostics: Optional list of skill diagnostics to retain for
                the runtime snapshot.
        """
        self._loaded_skills.extend(loads)
        if diagnostics is not None:
            self._skill_diagnostics.extend(diagnostics)

    def get_skills(self) -> list[SkillManifest]:
        """Get all loaded skill manifests."""
        return [load.manifest for load in self._loaded_skills]

    @property
    def skill_diagnostics(self) -> list[SkillDiagnostic]:
        """Diagnostics accumulated during skill discovery."""
        return list(self._skill_diagnostics)

    def get_skill_catalog(self) -> str:
        """Get the skill catalog formatted for system prompt injection.

        Returns a formatted string listing all discovered skills with their
        name, description, and location (source scope and path).
        """
        if self._suppress_skill_catalog:
            return ""

        if not self._loaded_skills:
            return ""

        lines = ["## Available Skills"]
        lines.append("")
        lines.append("The following skills are available for use. To activate a skill,")
        lines.append(
            "read its SKILL.md file using the `read` spell with the path shown below."
        )
        lines.append("")

        for skill_load in self._loaded_skills:
            manifest = skill_load.manifest
            lines.append(f"### {manifest.name}")
            lines.append(f"**Description:** {manifest.description}")
            lines.append(f"**Source:** {manifest.scope.value} ({manifest.path})")
            if manifest.version:
                lines.append(f"**Version:** {manifest.version}")
            lines.append("")

        return "\n".join(lines).strip()

    def suppress_skill_catalog(self, suppress: bool = True) -> None:
        """Suppress or enable skill catalog injection into system prompt.

        When suppressed, the skill catalog will not be included in the system
        prompt, allowing a rune (e.g., seeker) to own the skill surface.
        """
        self._suppress_skill_catalog = suppress

    def is_skill_catalog_suppressed(self) -> bool:
        """Check if skill catalog injection is suppressed."""
        return self._suppress_skill_catalog

    def send_message(self, content: str) -> None:
        self._message_queue.append(content)

    def set_session_name(self, name: str) -> None:
        self._session_name = name

    def create_api(self, rune_name: str | None = None) -> RuneAPI:
        if rune_name is None:
            rune_name = self._current_loading_rune
        return RuneAPI(self, rune_name)

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
