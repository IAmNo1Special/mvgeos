from __future__ import annotations

from collections.abc import Awaitable, Callable

from mvgeos_agent.types import SpellResult, SpellStatus

from coding_mvge.runes.skill_evolution.engine import SkillEvolutionEngine
from coding_mvge.runes.skill_evolution.proposer_mvge.spells.finish import (
    get_active_engine,
)


def make_read_file_spell(
    engine: SkillEvolutionEngine,
) -> Callable[[str], Awaitable[SpellResult]]:
    async def read_file(path: str) -> SpellResult:
        """Read a file safely within evolution store, traces, or skills."""
        return await engine.read_file(path)

    read_file.__name__ = "read_file"
    read_file.__doc__ = "Read a file safely within evolution store, traces, or skills."
    return read_file


async def read_file(path: str) -> SpellResult:
    """Read a file safely within evolution store, traces, or skills.

    Restricted strictly to skill_evolution/, raw_experience/, and discovered skills/.
    Supports reading pattern files (e.g. 'skill_evolution/patterns/retry.md'),
    raw execution traces (e.g. 'traces/task_123.json'), and skill files
    (e.g. 'skills/foo/SKILL.md').
    """
    target_engine = get_active_engine()
    if target_engine is None:
        return SpellResult(
            spell_name="read_file",
            status=SpellStatus.ERROR,
            error_message="No SkillEvolutionEngine available for read_file spell.",
        )
    return await target_engine.read_file(path)
