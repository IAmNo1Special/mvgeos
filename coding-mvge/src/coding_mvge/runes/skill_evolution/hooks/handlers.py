from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mvgeos_runes.types import (
    AfterInvocationData,
    SessionShutdownData,
    SessionStartData,
    SigilHook,
    TurnEndData,
)

logger = logging.getLogger(__name__)


class SkillEvolutionHooks:
    def __init__(
        self,
        harvester: Any,
        consolidator: Any,
        store: Any,
        subagent: Any | None = None,
    ) -> None:
        self.harvester = harvester
        self.consolidator = consolidator
        self.store = store
        self.subagent = subagent
        self.raw_experience_dir: Path | None = None

    def bind_raw(self, raw_dir: Path) -> None:
        self.raw_experience_dir = Path(raw_dir).expanduser().resolve()

    def set_subagent(self, subagent: Any) -> None:
        self.subagent = subagent

    async def on_after_invocation(self, data: AfterInvocationData) -> None:
        self.harvester.harvest(data.invocation)

    async def on_turn_end(self, data: TurnEndData) -> None:
        current_turn = getattr(data, "turn", 0)
        try:
            if self.consolidator.should_consolidate(current_turn):
                res = await self.consolidator.consolidate_batch(
                    current_turn=current_turn
                )
                if (
                    res
                    and (res.entries_created > 0 or res.entries_updated > 0)
                    and self.subagent is not None
                ):
                    await self.subagent.run(auto_apply=True)
        except Exception as exc:
            logger.warning("Skill evolution consolidation failed on turn_end: %s", exc)

    async def on_session_shutdown(self, data: SessionShutdownData) -> None:
        await self.store.flush()
        await self.harvester.persist_buffer()
        if self.raw_experience_dir:
            await self.harvester.persist_to_raw_experience(
                self.raw_experience_dir,
                getattr(data, "turn", 0) if hasattr(data, "turn") else 0,
            )

    async def on_session_start(self, data: SessionStartData) -> None:
        await self.harvester.load_buffer()

    def register(self, api: Any) -> None:
        api.on(SigilHook.AFTER_INVOCATION, self.on_after_invocation)
        api.on(SigilHook.TURN_END, self.on_turn_end)
        api.on(SigilHook.SESSION_SHUTDOWN, self.on_session_shutdown)
        api.on(SigilHook.SESSION_START, self.on_session_start)
