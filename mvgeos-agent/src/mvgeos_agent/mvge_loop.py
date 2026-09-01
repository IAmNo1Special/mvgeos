from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mvgeos_runes.types import SigilHook, SpellDefinition

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.core_loop import (
    EmitSink,
    LoopCallbacks,
    LoopContext,
    StreamFn,
    run_loop,
)
from mvgeos_agent.types import (
    AbortSignal,
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    QueueMode,
    SpellResultMessage,
    SummonerRequest,
)


class _RuneSpellWrapper(MvgeSpell):
    def __init__(self, spell_def: SpellDefinition) -> None:
        super().__init__(
            name=spell_def.name,
            description=spell_def.description,
            parameters=spell_def.parameters,
        )
        self._spell_def = spell_def

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return await self._spell_def.execute(spell_cast_id, params, signal, on_update)


_EVENT_TO_SIGIL: dict[MvgeEventType, SigilHook] = {
    MvgeEventType.AGENT_START: SigilHook.AGENT_START,
    MvgeEventType.AGENT_END: SigilHook.AGENT_END,
    MvgeEventType.COMPACTION_START: SigilHook.COMPACTION_START,
    MvgeEventType.COMPACTION_END: SigilHook.COMPACTION_END,
    MvgeEventType.TURN_START: SigilHook.TURN_START,
    MvgeEventType.TURN_END: SigilHook.TURN_END,
    MvgeEventType.INPUT: SigilHook.INPUT,
    MvgeEventType.BEFORE_PROVIDER_REQUEST: SigilHook.BEFORE_PROVIDER_REQUEST,
    MvgeEventType.AFTER_PROVIDER_RESPONSE: SigilHook.AFTER_PROVIDER_RESPONSE,
    MvgeEventType.BEFORE_INVOCATION: SigilHook.BEFORE_INVOCATION,
    MvgeEventType.AFTER_INVOCATION: SigilHook.AFTER_INVOCATION,
}


class MvgeLoop:
    """Stateful wrapper around the loop core.

    Owns the Rune runner, the event bus, and the Tome. Builds the core's emit
    sink and callbacks, then reduces the emitted events back into MvgeState.
    """

    def __init__(self, state: MvgeState) -> None:
        self._state = state
        self._after_invocation: (
            Callable[[list[MvgeInvocation]], Awaitable[list[MvgeInvocation] | None]]
            | None
        ) = None

    @property
    def state(self) -> MvgeState:
        return self._state

    @property
    def emit(self) -> EmitSink:
        """The sink that fans an event out to state, bus, Sigils, and Tome."""
        return self._emit

    def set_after_invocation(
        self,
        callback: Callable[
            [list[MvgeInvocation]], Awaitable[list[MvgeInvocation] | None]
        ],
    ) -> None:
        """Install a hook that runs after each Mvge Invocation.

        Used to let compaction swap the transcript between turns.
        """
        self._after_invocation = callback

    async def run(
        self,
        stream_fn: StreamFn,
        model: dict[str, Any],
        contemplation_level: str = "medium",
        signal: AbortSignal | None = None,
    ) -> MvgeInvocation:
        self._state.is_streaming = True
        self._state.model = model
        self._state.contemplation_level = ContemplationLevel(contemplation_level)

        context = LoopContext(
            system_prompt=self._state.system_prompt,
            prompt_source=self._state.prompt_source,
            invocations=list(self._state.invocations),
            spells=self._resolve_spells(),
            contemplation_level=self._state.contemplation_level,
            max_tokens=self._state.max_tokens,
            temperature=self._state.temperature,
            spell_timeout_ms=self._state.spell_timeout_ms,
            contemplation_budget=self._state.contemplation_budget,
            exclude_contemplation=self._state.exclude_contemplation,
            max_turns=self._state.max_turns,
            queue_mode=self._state.queue_mode,
        )

        try:
            new_invocations = await run_loop(
                context,
                stream_fn,
                self._emit,
                self._build_callbacks(),
                signal,
            )
        finally:
            self._state.is_streaming = False

        if new_invocations:
            return new_invocations[-1]
        if self._state.invocations:
            return self._state.invocations[-1]
        raise RuntimeError("No invocations to return")

    def _resolve_spells(self) -> list[MvgeSpell]:
        spells = list(self._state.spells)
        runner = self._state.rune_runner
        if runner is None:
            return spells
        known = {spell.name for spell in spells}
        for rune_spell in runner.get_all_registered_spells():
            if rune_spell.name not in known:
                spells.append(_RuneSpellWrapper(rune_spell))
        return spells

    async def _drain_steer_queue(self) -> list[MvgeInvocation]:
        if not self._state.steer_queue:
            return []
        if self._state.queue_mode == QueueMode.ONE_AT_A_TIME:
            return [self._state.steer_queue.pop(0)]
        queued: list[MvgeInvocation] = list(self._state.steer_queue)
        self._state.steer_queue.clear()
        return queued

    async def _drain_followup_queue(self) -> list[MvgeInvocation]:
        if not self._state.followup_queue:
            return []
        if self._state.queue_mode == QueueMode.ONE_AT_A_TIME:
            return [self._state.followup_queue.pop(0)]
        queued: list[MvgeInvocation] = list(self._state.followup_queue)
        self._state.followup_queue.clear()
        return queued

    def _build_callbacks(self) -> LoopCallbacks:
        runner = self._state.rune_runner
        if runner is None:
            return LoopCallbacks(
                get_steering_messages=self._drain_steer_queue,
                get_follow_up_messages=self._drain_followup_queue,
                after_invocation=self._after_invocation,
            )

        async def transform_context(
            invocations: list[MvgeInvocation],
        ) -> list[MvgeInvocation]:
            try:
                result = await runner.emit_chain(
                    SigilHook.CONTEXT_TRANSFORM, invocations
                )
            except Exception:
                return invocations
            if result is None:
                return invocations
            return list(result)

        async def before_realm_headers(headers: dict[str, str]) -> dict[str, str]:
            try:
                result = await runner.emit_chain(
                    SigilHook.BEFORE_PROVIDER_HEADERS, headers
                )
            except Exception:
                return headers
            if isinstance(result, dict):
                return {**headers, **result}
            return headers

        async def before_spell_cast(data: dict[str, Any]) -> dict[str, Any] | None:
            try:
                return await runner.emit_block(SigilHook.BEFORE_SPELL_CAST, data)
            except Exception:
                return None

        async def after_spell_result(data: dict[str, Any]) -> dict[str, Any]:
            try:
                result = await runner.emit_chain(SigilHook.AFTER_SPELL_RESULT, data)
            except Exception:
                return data
            if isinstance(result, dict):
                return result
            return data

        async def should_stop_after_turn() -> bool:
            try:
                result = await runner.emit_first(SigilHook.SHOULD_STOP_AFTER_TURN, {})
            except Exception:
                return False
            if isinstance(result, bool):
                return result
            return False

        async def prepare_next_turn(context: LoopContext) -> LoopContext:
            try:
                result = await runner.emit_chain(SigilHook.PREPARE_NEXT_TURN, context)
            except Exception:
                return context
            if isinstance(result, LoopContext):
                return result
            return context

        return LoopCallbacks(
            transform_context=transform_context,
            before_realm_headers=before_realm_headers,
            before_spell_cast=before_spell_cast,
            after_spell_result=after_spell_result,
            get_steering_messages=self._drain_steer_queue,
            get_follow_up_messages=self._drain_followup_queue,
            after_invocation=self._after_invocation,
            should_stop_after_turn=should_stop_after_turn,
            prepare_next_turn=prepare_next_turn,
        )

    async def _emit(self, event: MvgeEvent) -> None:
        self._reduce(event)
        self._record_event(event)

        bus = self._state.event_bus
        if bus is not None:
            bus.emit(event.type, event.data)

        runner = self._state.rune_runner
        hook = _EVENT_TO_SIGIL.get(event.type)
        if runner is not None and hook is not None:
            await runner.emit_async(hook, self._sigil_payload(event))

        if event.type == MvgeEventType.MESSAGE_END:
            await self._record_invocation(event)

    def _reduce(self, event: MvgeEvent) -> None:
        mana_used = event.data.get("mana_used")
        if isinstance(mana_used, int):
            self._state.mana_used = mana_used

        if event.type == MvgeEventType.BEFORE_PROVIDER_REQUEST:
            model = event.data.get("model")
            if isinstance(model, dict) and model.get("headers"):
                merged = {
                    **(self._state.model or {}).get("headers", {}),
                    **model["headers"],
                }
                self._state.model = {**(self._state.model or {}), "headers": merged}

        if event.type == MvgeEventType.INPUT:
            transformed = event.data.get("content")
            for inv in self._state.invocations:
                if isinstance(inv, SummonerRequest):
                    inv.content = transformed
                    break

        if event.type == MvgeEventType.MESSAGE_END:
            invocation = event.data.get("invocation")
            if invocation is not None and not isinstance(invocation, SummonerRequest):
                self._state.invocations.append(invocation)

    def _record_event(self, event: MvgeEvent) -> None:
        if len(self._state.events) >= self._state.max_events:
            self._state.events = self._state.events[-self._state.max_events // 2 :]
        self._state.events.append(event)

    def _sigil_payload(self, event: MvgeEvent) -> Any:
        if event.type == MvgeEventType.AFTER_PROVIDER_RESPONSE:
            return {"response": event.data.get("response")}
        return event.data

    async def _record_invocation(self, event: MvgeEvent) -> None:
        session: MvgeTome | None = self._state.agent_tome
        if session is None:
            return
        invocation = event.data.get("invocation")
        if invocation is None:
            return

        parent_id = await session.active_leaf_id_async()
        model = self._state.model or {}
        if isinstance(invocation, SummonerRequest):
            await session.record_message_async(
                role="user",
                content=invocation.content,
                parent_id=parent_id,
            )
        elif isinstance(invocation, MvgeResponse):
            await session.record_message_async(
                role="assistant",
                content=invocation.content,
                parent_id=parent_id,
                model=model.get("id", ""),
                provider=model.get("id", "").split("/")[0],
            )
        elif isinstance(invocation, SpellResultMessage):
            await session.record_message_async(
                role="tool",
                content=invocation.content,
                parent_id=parent_id,
            )


__all__ = [
    "MvgeLoop",
]
