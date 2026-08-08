from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from mvgeos_agent.compaction_runner import CompactionRunner
from mvgeos_agent.loop import (
    LoopCallbacks,
    LoopContext,
    MvgeLoop,
    StreamFn,
    _drain,
    _resolve_model,
    _RunState,
    _TurnOutcome,
)
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

    The harness implements Pi's nested loop structure:
    - Outer loop: resumes when follow-ups arrive after the Mvge would settle
    - Inner loop: drives turns via MvgeLoop.run() while spells cast or messages queued
    - After each Mvge Invocation: calls CompactionRunner.maybe_compact()
    - Calls should_stop_after_turn() after each turn; if true, breaks gracefully
    - Calls prepare_next_turn(context) before each new turn
    - Drains steering/follow-up queues between inner/outer loops
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
        """Run the harness, driving the session through outer/inner loops."""
        self._loop.state.is_streaming = True
        self._loop.state.model = model
        self._loop.state.contemplation_level = ContemplationLevel(contemplation_level)

        context = LoopContext(
            system_prompt=self._loop.state.system_prompt,
            invocations=list(self._loop.state.invocations),
            spells=self._loop._resolve_spells(),
            contemplation_level=self._loop.state.contemplation_level,
            max_tokens=self._loop.state.max_tokens,
            temperature=self._loop.state.temperature,
            spell_timeout_ms=self._loop.state.spell_timeout_ms,
            contemplation_budget=self._loop.state.contemplation_budget,
            exclude_contemplation=self._loop.state.exclude_contemplation,
            max_turns=self._loop.state.max_turns,
        )

        state = _RunState()
        invocations = list(context.invocations)
        new_invocations: list[MvgeInvocation] = []

        await self._emit(MvgeEvent(type=MvgeEventType.AGENT_START, data={}))

        if self._callbacks.transform_context is not None:
            invocations = await self._callbacks.transform_context(invocations)

        initial = next(
            (inv for inv in invocations if isinstance(inv, SummonerRequest)),
            None,
        )
        if initial is not None:
            await self._emit(
                MvgeEvent(type=MvgeEventType.INPUT, data={"content": initial.content})
            )
            await self._emit(
                MvgeEvent(
                    type=MvgeEventType.MESSAGE_END,
                    data={"invocation": initial, "mana_used": state.mana_used},
                )
            )

        model_resolved = await _resolve_model(self._callbacks)
        pending: list[MvgeInvocation] = []
        turns = 0

        # Outer loop: resumes when follow-ups arrive after the Mvge would settle.
        while True:
            keep_going = True

            # Inner loop: another turn while Spells were cast or messages queued.
            while keep_going or pending:
                turns += 1
                if turns > context.max_turns:
                    raise RuntimeError("Max turns exceeded")

                # Call prepare_next_turn before each turn (except the first)
                if turns > 1 and self._callbacks.prepare_next_turn is not None:
                    context = await self._callbacks.prepare_next_turn(context)

                for queued in pending:
                    invocations.append(queued)
                    new_invocations.append(queued)
                    await self._emit(
                        MvgeEvent(
                            type=MvgeEventType.MESSAGE_END,
                            data={"invocation": queued, "mana_used": state.mana_used},
                        )
                    )
                pending = []

                await self._emit(
                    MvgeEvent(
                        type=MvgeEventType.BEFORE_PROVIDER_REQUEST,
                        data={"model": model_resolved},
                    )
                )
                await self._emit(
                    MvgeEvent(
                        type=MvgeEventType.TURN_START,
                        data={"model": model_resolved},
                    )
                )

                turn = await self._run_turn(
                    context, stream_fn, self._emit, self._callbacks, invocations, state
                )
                invocations.extend(turn.produced)
                new_invocations.extend(turn.produced)

                # Run compaction after each Mvge Invocation
                if turn.produced and self._compaction is not None:
                    replacement = await self._compaction.maybe_compact(
                        list(invocations)
                    )
                    if replacement is not None:
                        invocations = list(replacement)

                # Also call after_invocation callback for Rune-specific
                # transcript mutations
                if turn.produced and self._callbacks.after_invocation is not None:
                    replacement = await self._callbacks.after_invocation(
                        list(invocations)
                    )
                    if replacement is not None:
                        invocations = list(replacement)

                await self._emit(
                    MvgeEvent(
                        type=MvgeEventType.TURN_END,
                        data={
                            "stop_reason": turn.stop_reason,
                            "mana_used": state.mana_used,
                        },
                    )
                )

                # Check if we should stop after this turn
                if self._callbacks.should_stop_after_turn is not None:
                    should_stop = await self._callbacks.should_stop_after_turn()
                    if should_stop:
                        # Gracefully exit both loops
                        await self._emit(
                            MvgeEvent(
                                type=MvgeEventType.AGENT_END,
                                data={"stop_reason": state.last_stop_reason},
                            )
                        )
                        # Return the last MvgeResponse, not SpellResultMessage
                        for inv in reversed(new_invocations):
                            if isinstance(inv, MvgeResponse):
                                return inv
                        last_new = new_invocations[-1] if new_invocations else None
                        last_inv = invocations[-1] if invocations else None
                        result = last_new if last_new is not None else last_inv
                        if result is None:
                            raise RuntimeError("No invocations to return")
                        return result

                keep_going = turn.cast_spells
                if not keep_going:
                    pending = await _drain(self._callbacks.get_steering_messages)

            follow_ups = await _drain(self._callbacks.get_follow_up_messages)
            if follow_ups:
                pending = follow_ups
                continue
            break

        await self._emit(
            MvgeEvent(
                type=MvgeEventType.AGENT_END,
                data={"stop_reason": state.last_stop_reason},
            )
        )
        return new_invocations[-1] if new_invocations else invocations[-1]

    async def _emit(self, event: MvgeEvent) -> None:
        """Emit event through the loop's emit sink."""
        await self._loop.emit(event)

    async def _run_turn(
        self,
        context: LoopContext,
        stream_fn: StreamFn,
        emit: Callable[[MvgeEvent], Any],
        callbacks: LoopCallbacks,
        invocations: list[MvgeInvocation],
        state: _RunState,
    ) -> _TurnOutcome:
        """Channel one Realm response and cast any Spells it requests."""
        from mvgeos_agent.loop import _run_turn as core_run_turn

        return await core_run_turn(
            context, stream_fn, emit, callbacks, invocations, state
        )
