from __future__ import annotations

from typing import Any

from mvgeos_runes.types import SpellDefinition

from .consolidate import SPELL as CONSOLIDATE_SPELL
from .consolidate import execute as consolidate_execute
from .export import SPELL as EXPORT_SPELL
from .export import execute as export_execute


def make_consolidate_spell(consolidator: Any) -> SpellDefinition:
    spell = CONSOLIDATE_SPELL

    async def wrapped(
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return await consolidate_execute(params, signal, on_update, consolidator)

    setattr(spell, "execute", wrapped)  # noqa: B010
    return spell


def make_export_spell(knowledge: Any, agent_name: str) -> SpellDefinition:
    spell = EXPORT_SPELL

    async def wrapped(
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return await export_execute(params, signal, on_update, knowledge, agent_name)

    setattr(spell, "execute", wrapped)  # noqa: B010
    return spell


__all__ = [
    "make_consolidate_spell",
    "make_export_spell",
]
