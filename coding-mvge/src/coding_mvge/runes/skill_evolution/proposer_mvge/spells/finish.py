from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)

from coding_mvge.runes.skill_evolution.engine import SkillEvolutionEngine

_ACTIVE_ENGINE: ContextVar[SkillEvolutionEngine | None] = ContextVar(
    "active_engine", default=None
)


def get_active_engine() -> SkillEvolutionEngine | None:
    return _ACTIVE_ENGINE.get()


def set_active_engine(engine: SkillEvolutionEngine | None) -> None:
    _ACTIVE_ENGINE.set(engine)


def make_finish_spell(
    engine: SkillEvolutionEngine,
) -> Callable[[dict[str, Any] | str], Awaitable[SpellResult]]:
    async def finish(proposal: dict[str, Any] | str) -> SpellResult:
        """Submit the final skill proposal."""
        return await _execute_finish(proposal, engine)

    finish.__name__ = "finish"
    finish.__doc__ = (
        "Submit the final skill proposal. Validates schema, records the proposal "
        "to the skill-impact audit trail, and applies changes if auto_apply is enabled."
    )
    return finish


async def finish(proposal: dict[str, Any] | str) -> SpellResult:
    """Submit the final skill proposal.

    Validates schema, records the proposal to the skill-impact audit trail,
    and applies changes to the target skills directory if enabled.
    """
    target_engine = get_active_engine()
    if target_engine is None:
        return SpellResult(
            spell_name="finish",
            status=SpellStatus.ERROR,
            error_message="No SkillEvolutionEngine available for finish spell.",
        )
    return await _execute_finish(proposal, target_engine)


async def _execute_finish(
    proposal: dict[str, Any] | str, engine: SkillEvolutionEngine
) -> SpellResult:
    res = await engine.apply_proposal(proposal)
    if res.success:
        return SpellResult(
            spell_name="finish",
            status=SpellStatus.SUCCESS,
            content=json.dumps(res.to_dict()),
        )
    return SpellResult(
        spell_name="finish",
        status=SpellStatus.ERROR,
        error_message=res.error or "Proposal rejected",
    )
