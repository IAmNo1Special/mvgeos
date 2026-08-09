from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from mvgeos_agent.compaction_runner import CompactionRunner
from mvgeos_agent.loop import LoopCallbacks, LoopContext, MvgeLoop, StreamFn
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
    SpellResultMessage,
    StopReason,
    SummonerRequest,
)
from mvgeos_provider.types import Model, RealmResponse


class MvgeHarness:
    """Wraps MvgeLoop and owns the session lifecycle (matching Pi's AgentHarness).

    The harness implements Pi's nested loop structure by configuring the loop's
    callbacks and calling MvgeLoop.run():
    - Compaction runs via after_invocation callback
    - should_stop_after_turn/prepare_next_turn via callbacks
    - Steering/follow-up queues handled by loop's built-in logic
    """

    def __init__(
        self,
        loop: MvgeLoop,
        compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        self._loop = loop
        self._compaction = compaction
        self._callbacks = callbacks

    async def run(
        self,
        stream_fn: StreamFn,
        model: dict[str, Any],
        contemplation_level: str = "medium",
    ) -> MvgeInvocation:
        """Run the harness by delegating to MvgeLoop.run()."""
        # The loop's run() already handles the full nested loop structure
        # (outer for follow-ups, inner for spells/steering) via run_loop()
        # Our callbacks handle compaction, stop checks, and turn preparation
        return await self._loop.run(
            stream_fn=stream_fn,
            model=model,
            contemplation_level=contemplation_level,
        )
