from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mvgeos_agent.loop import LoopCallbacks, MvgeLoop, StreamFn

from mvgeos_agent.harness.compaction.compaction_runner import CompactionRunner
from mvgeos_agent.types import MvgeInvocation


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
        compaction: CompactionRunner | None = None,
        callbacks: LoopCallbacks | None = None,
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
        callbacks = self._callbacks or self._loop._build_callbacks()
        original_after_invocation = callbacks.after_invocation

        async def after_invocation_with_compaction(
            invocations: list[MvgeInvocation],
        ) -> list[MvgeInvocation] | None:
            if self._compaction is not None:
                replacement = await self._compaction.maybe_compact(list(invocations))
                if replacement is not None:
                    invocations = list(replacement)
            if original_after_invocation is not None:
                replacement = await original_after_invocation(list(invocations))
                if replacement is not None:
                    invocations = list(replacement)
            return invocations

        callbacks.after_invocation = after_invocation_with_compaction

        return await self._loop.run(
            stream_fn=stream_fn,
            model=model,
            contemplation_level=contemplation_level,
            callbacks=callbacks,
        )


__all__ = ["MvgeHarness"]
