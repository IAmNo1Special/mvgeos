from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_runes.types import (
    AfterInvocationData,
    SessionShutdownData,
    SessionStartData,
    TurnEndData,
)

from coding_mvge.runes.skill_evolution.hooks.handlers import SkillEvolutionHooks


@pytest.mark.asyncio
async def test_skill_evolution_hooks_lifecycle(tmp_path: Path) -> None:
    harvester = MagicMock()
    harvester.harvest = MagicMock()
    harvester.persist_buffer = AsyncMock()
    harvester.persist_to_raw_experience = AsyncMock()
    harvester.load_buffer = AsyncMock()

    consolidator = MagicMock()
    consolidator.should_consolidate = MagicMock(return_value=True)
    consolidation_res = MagicMock()
    consolidation_res.entries_created = 1
    consolidation_res.entries_updated = 0
    consolidator.consolidate_batch = AsyncMock(return_value=consolidation_res)

    store = MagicMock()
    store.flush = AsyncMock()

    subagent = MagicMock()
    subagent.run = AsyncMock(return_value={"success": True})

    hooks = SkillEvolutionHooks(
        harvester=harvester,
        consolidator=consolidator,
        store=store,
        subagent=subagent,
    )
    hooks.bind_raw(tmp_path / "raw")
    hooks.set_subagent(subagent)

    # 1. on_after_invocation
    inv_data = MagicMock(spec=AfterInvocationData)
    inv_data.invocation = MagicMock()
    await hooks.on_after_invocation(inv_data)
    harvester.harvest.assert_called_once_with(inv_data.invocation)

    # 2. on_turn_end
    turn_data = MagicMock(spec=TurnEndData)
    turn_data.turn = 5
    await hooks.on_turn_end(turn_data)
    consolidator.should_consolidate.assert_called_once_with(5)
    consolidator.consolidate_batch.assert_called_once_with(current_turn=5)
    subagent.run.assert_called_once_with(auto_apply=True)

    # 3. on_session_shutdown
    shutdown_data = MagicMock(spec=SessionShutdownData)
    shutdown_data.turn = 10
    await hooks.on_session_shutdown(shutdown_data)
    store.flush.assert_called_once()
    harvester.persist_buffer.assert_called_once()
    harvester.persist_to_raw_experience.assert_called_once()

    # 4. on_session_start
    start_data = MagicMock(spec=SessionStartData)
    await hooks.on_session_start(start_data)
    harvester.load_buffer.assert_called_once()

    # 5. register
    api = MagicMock()
    hooks.register(api)
    assert api.on.call_count == 4


@pytest.mark.asyncio
async def test_on_turn_end_exception_resilience() -> None:
    harvester = MagicMock()
    consolidator = MagicMock()
    consolidator.should_consolidate = MagicMock(return_value=True)
    consolidator.consolidate_batch = AsyncMock(
        side_effect=RuntimeError("No LLM completion available for consolidation")
    )
    store = MagicMock()

    hooks = SkillEvolutionHooks(
        harvester=harvester,
        consolidator=consolidator,
        store=store,
    )
    turn_data = MagicMock(spec=TurnEndData)
    turn_data.turn = 5

    # Should not raise exception
    await hooks.on_turn_end(turn_data)
    consolidator.consolidate_batch.assert_called_once_with(current_turn=5)
