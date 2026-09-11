from __future__ import annotations

from typing import Any

from mvgeos_core.spells import ExecutionMode
from mvgeos_runes.types import SpellDefinition


def make_consolidate_spell(consolidator: Any) -> SpellDefinition:
    async def execute(
        params: dict[str, Any], signal: Any = None, on_update: Any = None
    ) -> dict[str, Any]:
        force = params.get("force", False)
        current_turn = int(params.get("current_turn", 0))
        result = await consolidator.consolidate_batch(
            current_turn=current_turn, force=force
        )
        if result is None:
            return {
                "consolidated": False,
                "reason": "No traces or thresholds not met",
                "buffer_stats": consolidator.harvester.get_stats(),
            }
        return {
            "consolidated": True,
            "entries_created": result.entries_created,
            "entries_updated": result.entries_updated,
            "duration_ms": result.duration_ms,
            "traces_processed": result.log_entry.traces_processed,
        }

    return SpellDefinition(
        name="skill_evolution_consolidate",
        description=(
            "Manually trigger raw_experience -> skill_evolution consolidation "
            "(ExperienceConsolidator) per WikiSkill arxiv:2608.27454 §3.2.2"
        ),
        parameters={
            "type": "object",
            "properties": {
                "force": {"type": "boolean", "description": "Force operation"},
                "current_turn": {
                    "type": "string",
                    "description": "Current turn number",
                },
            },
        },
        execution_mode=ExecutionMode.SEQUENTIAL,
        prompt_snippet="Force skill evolution experience consolidation.",
        source_rune="skill_evolution",
        handler=execute,
    )
