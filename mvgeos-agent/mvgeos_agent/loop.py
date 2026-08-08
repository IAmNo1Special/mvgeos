from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from mvgeos_provider.types import RealmResponse
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook, SpellDefinition

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.errors import (
    AuthenticationError,
    MvgeError,
    RateLimitError,
    SpellNotFoundError,
    SpellTimeoutError,
    to_error,
)
from mvgeos_agent.types import (
    ContemplationLevel,
    ContentType,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    SpellResultMessage,
    StopReason,
    SummonerRequest,
)

EmitSink = Callable[[MvgeEvent], Awaitable[None]]
StreamFn = Callable[[list[MvgeInvocation]], AsyncIterator[RealmResponse]]

_TRUNCATED_SPELL_CALL = (
    "Spell '{name}' was not cast: the response hit the output Mana limit, so its "
    "arguments may be truncated. Re-issue the spell cast with complete arguments."
)


@dataclass(frozen=True)
class LoopContext:
    """Immutable snapshot of everything the loop core reads.

    The core never sees the Rune runner, the Tome, or the event bus. Those are
    the wrapper's concern; the core reaches the outside world only through its
    emit sink and its callbacks.
    """

    system_prompt: str = ""
    invocations: list[MvgeInvocation] = field(default_factory=list)
    spells: list[MvgeSpell] = field(default_factory=list)
    contemplation_level: ContemplationLevel = ContemplationLevel.MEDIUM
    max_tokens: int | None = None
    temperature: float | None = None
    spell_timeout_ms: int = 30000
    contemplation_budget: int | None = None
    exclude_contemplation: bool = False
    max_turns: int = 50


@dataclass
class LoopCallbacks:
    """Value-returning extension points for the loop core.

    Every callback is optional. Each one must not raise: return a safe fallback
    value instead. The wrapper honours this contract when it builds callbacks
    from a Rune runner.
    """

    transform_context: (
        Callable[[list[MvgeInvocation]], Awaitable[list[MvgeInvocation]]] | None
    ) = None
    before_realm_headers: (
        Callable[[dict[str, str]], Awaitable[dict[str, str]]] | None
    ) = None
    before_spell_cast: (
        Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    ) = None
    after_spell_result: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = (
        None
    )
    get_steering_messages: Callable[[], Awaitable[list[MvgeInvocation]]] | None = None
    get_follow_up_messages: Callable[[], Awaitable[list[MvgeInvocation]]] | None = None
    # Runs after each Mvge Invocation. Return a replacement transcript to swap
    # what the next turn sends (this is how compaction takes effect), or None
    # to leave it untouched.
    #
    # DEPRECATED: Compaction is now owned by MvgeHarness via its own
    # after_invocation callback. This callback is kept only for Rune-specific
    # transcript mutations via the AFTER_INVOCATION sigil hook.
    after_invocation: (
        Callable[[list[MvgeInvocation]], Awaitable[list[MvgeInvocation] | None]] | None
    ) = None
    # Called after each turn. Return True to gracefully stop the Mvge after the
    # current turn completes.
    should_stop_after_turn: Callable[[], Awaitable[bool]] | None = None
    # Called before each new turn. Allows modifying the context (model,
    # contemplation, spells, etc.) for the next turn.
    prepare_next_turn: Callable[[LoopContext], Awaitable[LoopContext]] | None = None


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
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return await self._spell_def.execute(spell_cast_id, params, signal, on_update)


async def run_loop(
    context: LoopContext,
    stream_fn: StreamFn,
    emit: EmitSink,
    callbacks: LoopCallbacks,
) -> list[MvgeInvocation]:
    """Drive the Realm turn by turn, casting Spells as they are requested.

    The loop owns the turn cycle: it calls `stream_fn` once per turn with the
    running transcript, channels the responses, casts any Spells, and goes
    round again while Spell results, steering, or follow-ups remain.

    Returns the Invocations produced by this run. The caller reduces any state
    it keeps from the emitted events.
    """
    if not context.invocations:
        raise RuntimeError("No invocations to process")

    invocations = list(context.invocations)
    new_invocations: list[MvgeInvocation] = []
    state = _RunState()

    await emit(MvgeEvent(type=MvgeEventType.AGENT_START, data={}))

    if callbacks.transform_context is not None:
        invocations = await callbacks.transform_context(invocations)

    initial = next(
        (inv for inv in invocations if isinstance(inv, SummonerRequest)),
        None,
    )
    if initial is not None:
        await emit(
            MvgeEvent(type=MvgeEventType.INPUT, data={"content": initial.content})
        )
        await emit(
            MvgeEvent(
                type=MvgeEventType.MESSAGE_END,
                data={"invocation": initial, "mana_used": state.mana_used},
            )
        )

    model = await _resolve_model(callbacks)
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
            if turns > 1 and callbacks.prepare_next_turn is not None:
                context = await callbacks.prepare_next_turn(context)

            for queued in pending:
                invocations.append(queued)
                new_invocations.append(queued)
                await emit(
                    MvgeEvent(
                        type=MvgeEventType.MESSAGE_END,
                        data={"invocation": queued, "mana_used": state.mana_used},
                    )
                )
            pending = []

            await emit(
                MvgeEvent(
                    type=MvgeEventType.BEFORE_PROVIDER_REQUEST, data={"model": model}
                )
            )
            await emit(MvgeEvent(type=MvgeEventType.TURN_START, data={"model": model}))

            turn = await _run_turn(
                context, stream_fn, emit, callbacks, invocations, state
            )
            invocations.extend(turn.produced)
            new_invocations.extend(turn.produced)

            if turn.produced and callbacks.after_invocation is not None:
                replacement = await callbacks.after_invocation(list(invocations))
                if replacement is not None:
                    invocations = list(replacement)

            await emit(
                MvgeEvent(
                    type=MvgeEventType.TURN_END,
                    data={
                        "stop_reason": turn.stop_reason,
                        "mana_used": state.mana_used,
                    },
                )
            )

            # Check if we should stop after this turn
            if callbacks.should_stop_after_turn is not None:
                should_stop = await callbacks.should_stop_after_turn()
                if should_stop:
                    # Gracefully exit both loops
                    await emit(
                        MvgeEvent(
                            type=MvgeEventType.AGENT_END,
                            data={"stop_reason": state.last_stop_reason},
                        )
                    )
                    return new_invocations

            keep_going = turn.cast_spells
            if not keep_going:
                pending = await _drain(callbacks.get_steering_messages)

        follow_ups = await _drain(callbacks.get_follow_up_messages)
        if follow_ups:
            pending = follow_ups
            continue
        break

    await emit(
        MvgeEvent(
            type=MvgeEventType.AGENT_END,
            data={"stop_reason": state.last_stop_reason},
        )
    )
    return new_invocations


@dataclass
class _RunState:
    """Mutable bookkeeping threaded through a single run."""

    mana_used: int = 0
    last_stop_reason: StopReason | None = None


@dataclass
class _TurnOutcome:
    """What one turn produced."""

    produced: list[MvgeInvocation] = field(default_factory=list)
    stop_reason: StopReason | None = None
    cast_spells: bool = False


async def _drain(
    source: Callable[[], Awaitable[list[MvgeInvocation]]] | None,
) -> list[MvgeInvocation]:
    if source is None:
        return []
    return list(await source())


async def _resolve_model(callbacks: LoopCallbacks) -> dict[str, Any]:
    model: dict[str, Any] = {}
    headers: dict[str, str] = {}
    if callbacks.before_realm_headers is not None:
        headers = await callbacks.before_realm_headers(headers)
    if headers:
        model = {**model, "headers": headers}
    return model


async def _run_turn(
    context: LoopContext,
    stream_fn: StreamFn,
    emit: EmitSink,
    callbacks: LoopCallbacks,
    invocations: list[MvgeInvocation],
    state: _RunState,
) -> _TurnOutcome:
    """Channel one Realm response and cast any Spells it requests."""
    outcome = _TurnOutcome()

    async for response in stream_fn(list(invocations)):
        if response.error_message:
            error_code = getattr(response, "error_code", None)
            if error_code == "rate_limited":
                raise RateLimitError(response.error_message)
            if error_code == "auth_failed":
                raise AuthenticationError(response.error_message)
            raise RuntimeError(response.error_message)

        state.mana_used += response.mana_used

        await emit(
            MvgeEvent(
                type=MvgeEventType.AFTER_PROVIDER_RESPONSE,
                data={"response": response, "mana_used": state.mana_used},
            )
        )

        if response.invocation is None:
            continue

        inv: MvgeResponse = response.invocation
        for item in inv.content or []:
            if item.get("type") == ContentType.TEXT:
                await emit(
                    MvgeEvent(
                        type=MvgeEventType.MESSAGE_UPDATE,
                        data={"text": item.get("text", "")},
                    )
                )

        if inv.stop_reason == StopReason.PENDING:
            continue

        await emit(
            MvgeEvent(type=MvgeEventType.BEFORE_INVOCATION, data={"invocation": inv})
        )

        spell_results = await _cast_requested_spells(
            context, inv, emit, callbacks, state
        )

        await emit(
            MvgeEvent(
                type=MvgeEventType.AFTER_INVOCATION,
                data={"invocation": inv, "stop_reason": inv.stop_reason},
            )
        )

        outcome.produced.append(inv)
        outcome.stop_reason = inv.stop_reason
        state.last_stop_reason = inv.stop_reason
        await emit(
            MvgeEvent(
                type=MvgeEventType.MESSAGE_END,
                data={"invocation": inv, "mana_used": state.mana_used},
            )
        )

        for spell_result in spell_results:
            outcome.produced.append(spell_result)
            await emit(
                MvgeEvent(
                    type=MvgeEventType.MESSAGE_END,
                    data={"invocation": spell_result, "mana_used": state.mana_used},
                )
            )

        # Truncated calls were refused, not cast, so they do not earn a turn.
        outcome.cast_spells = (
            bool(spell_results) and inv.stop_reason == StopReason.SPELL_USE
        )
        return outcome

    return outcome


async def _cast_requested_spells(
    context: LoopContext,
    inv: MvgeResponse,
    emit: EmitSink,
    callbacks: LoopCallbacks,
    state: _RunState,
) -> list[SpellResultMessage]:
    tool_calls = [
        item["tool_call"]
        for item in inv.content or []
        if item.get("type") == ContentType.TOOL_CALL
    ]
    if not tool_calls:
        return []

    # A LENGTH stop means the response was cut off mid-stream, so every Spell
    # call in it may carry truncated arguments. None are safe to cast; report
    # each as an error so the Mvge can re-issue it.
    if inv.stop_reason == StopReason.LENGTH:
        truncated: list[SpellResultMessage] = []
        for tool_call in tool_calls:
            await _emit_truncated(tool_call, emit)
            truncated.append(_truncated_result(tool_call))
        return truncated

    results: list[SpellResultMessage] = []
    for tool_call in tool_calls:
        if callbacks.before_spell_cast is not None:
            blocked = await callbacks.before_spell_cast(
                {"tool_call": tool_call, "spell_name": tool_call["name"]}
            )
            if blocked:
                continue
        result = await _cast_spell(context, tool_call, emit, callbacks)
        if result is not None:
            results.append(result)
    return results


async def _emit_truncated(tool_call: dict[str, Any], emit: EmitSink) -> None:
    message = _TRUNCATED_SPELL_CALL.format(name=tool_call["name"])
    await emit(
        MvgeEvent(
            type=MvgeEventType.SPELL_CASTING_START,
            data={"spellCastId": tool_call["id"], "spellName": tool_call["name"]},
        )
    )
    await emit(
        MvgeEvent(
            type=MvgeEventType.SPELL_CASTING_END,
            data={"spellCastId": tool_call["id"], "error": message},
        )
    )


def _truncated_result(tool_call: dict[str, Any]) -> SpellResultMessage:
    return SpellResultMessage(
        spell_cast_id=tool_call["id"],
        spell_name=tool_call["name"],
        content=[
            {
                "type": "text",
                "text": _TRUNCATED_SPELL_CALL.format(name=tool_call["name"]),
            }
        ],
        is_error=True,
    )


async def _cast_spell(
    context: LoopContext,
    tool_call: dict[str, Any],
    emit: EmitSink,
    callbacks: LoopCallbacks,
) -> SpellResultMessage | None:
    spell_name = tool_call["name"]
    spell = next((s for s in context.spells if s.name == spell_name), None)

    if spell is None:
        err: MvgeError = SpellNotFoundError(spell_name)
        await emit(
            MvgeEvent(
                type=MvgeEventType.SPELL_CASTING_END,
                data={
                    "spellCastId": tool_call["id"],
                    "error": err.code,
                    "message": str(err),
                },
            )
        )
        return None

    await emit(
        MvgeEvent(
            type=MvgeEventType.SPELL_CASTING_START,
            data={"spellCastId": tool_call["id"], "spellName": spell_name},
        )
    )

    try:
        result = await asyncio.wait_for(
            spell.execute(tool_call["id"], tool_call.get("arguments", {})),
            timeout=context.spell_timeout_ms / 1000,
        )
        result_content: Any = result
        if callbacks.after_spell_result is not None:
            chained = await callbacks.after_spell_result(
                {
                    "spell_name": spell_name,
                    "spell_cast_id": tool_call["id"],
                    "result": result,
                }
            )
            if isinstance(chained, dict):
                result_content = chained.get("result", result)

        await emit(
            MvgeEvent(
                type=MvgeEventType.SPELL_CASTING_END,
                data={"spellCastId": tool_call["id"], "result": result_content},
            )
        )
        return SpellResultMessage(
            spell_cast_id=tool_call["id"],
            spell_name=spell_name,
            content=[{"type": "text", "text": str(result_content)}],
            is_error=False,
        )
    except TimeoutError:
        err = SpellTimeoutError(spell_name, context.spell_timeout_ms)
    except Exception as exc:
        err = to_error(exc)

    await emit(
        MvgeEvent(
            type=MvgeEventType.SPELL_CASTING_END,
            data={"spellCastId": tool_call["id"], "error": str(err)},
        )
    )
    return SpellResultMessage(
        spell_cast_id=tool_call["id"],
        spell_name=spell_name,
        content=[{"type": "text", "text": str(err)}],
        is_error=True,
    )


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
    ) -> MvgeInvocation:
        self._state.is_streaming = True
        self._state.model = model
        self._state.contemplation_level = ContemplationLevel(contemplation_level)

        context = LoopContext(
            system_prompt=self._state.system_prompt,
            invocations=list(self._state.invocations),
            spells=self._resolve_spells(),
            contemplation_level=self._state.contemplation_level,
            max_tokens=self._state.max_tokens,
            temperature=self._state.temperature,
            spell_timeout_ms=self._state.spell_timeout_ms,
            contemplation_budget=self._state.contemplation_budget,
            exclude_contemplation=self._state.exclude_contemplation,
            max_turns=self._state.max_turns,
        )

        try:
            new_invocations = await run_loop(
                context,
                stream_fn,
                self._emit,
                self._build_callbacks(),
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
        queued: list[MvgeInvocation] = list(self._state.steer_queue)
        self._state.steer_queue.clear()
        return queued

    async def _drain_followup_queue(self) -> list[MvgeInvocation]:
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
            self._record_invocation(event)

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

    def _record_invocation(self, event: MvgeEvent) -> None:
        session: MvgeTome | None = self._state.agent_session
        if session is None:
            return
        invocation = event.data.get("invocation")
        if invocation is None:
            return

        model = self._state.model or {}
        if isinstance(invocation, SummonerRequest):
            session.record_message(role="user", content=invocation.content)
        elif isinstance(invocation, MvgeResponse):
            session.record_message(
                role="assistant",
                content=invocation.content,
                model=model.get("id", ""),
                provider=model.get("id", "").split("/")[0],
            )
        elif isinstance(invocation, SpellResultMessage):
            session.record_message(
                role="tool",
                content=str(invocation.content),
            )


__all__ = [
    "EmitSink",
    "LoopCallbacks",
    "LoopContext",
    "MvgeLoop",
    "RuneRunner",
    "run_loop",
]
