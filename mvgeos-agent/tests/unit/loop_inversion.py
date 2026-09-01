from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_provider.types import Model, RealmResponse

from mvgeos_agent.core_loop import LoopCallbacks, LoopContext, run_loop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
    QueueMode,
    SpellResultMessage,
    StopReason,
    SummonerRequest,
)


def _model() -> Model:
    return Model(
        id="test-model",
        name="Test Model",
        realm="test",
        base_url="https://api.test.com",
        api_key="test",
    )


def _text(text: str = "Hello!", stop: StopReason = StopReason.STOP) -> RealmResponse:
    return RealmResponse(
        model=_model(),
        invocation=MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": text}],
            stop_reason=stop,
        ),
    )


def _spell_call(
    name: str = "test_spell",
    call_id: str = "call-1",
    stop: StopReason = StopReason.SPELL_USE,
) -> RealmResponse:
    return RealmResponse(
        model=_model(),
        invocation=MvgeResponse(
            role="assistant",
            content=[
                {
                    "type": "spell_cast",
                    "spell_cast": {"id": call_id, "name": name, "arguments": {}},
                }
            ],
            stop_reason=stop,
        ),
    )


class Recorder:
    def __init__(self) -> None:
        self.events: list[MvgeEvent] = []

    async def __call__(self, event: MvgeEvent) -> None:
        self.events.append(event)

    def types(self) -> list[MvgeEventType]:
        return [event.type for event in self.events]

    def count(self, event_type: MvgeEventType) -> int:
        return sum(1 for event in self.events if event.type == event_type)

    def of_type(self, event_type: MvgeEventType) -> list[MvgeEvent]:
        return [event for event in self.events if event.type == event_type]


class TurnScript:
    """A StreamFn that yields a scripted set of responses per turn."""

    def __init__(self, turns: list[list[RealmResponse]]) -> None:
        self._turns = turns
        self.calls: list[list[MvgeInvocation]] = []

    def __call__(
        self, invocations: list[Any], signal: Any | None = None
    ) -> AsyncIterator[RealmResponse]:
        self.calls.append(list(invocations))
        index = min(len(self.calls) - 1, len(self._turns) - 1)
        responses = self._turns[index]

        async def gen() -> AsyncIterator[RealmResponse]:
            for response in responses:
                yield response

        return gen()


@pytest.fixture
def spell() -> MvgeSpell:
    stub = MagicMock(spec=MvgeSpell)
    stub.name = "test_spell"
    stub.description = "A test spell"
    stub.parameters = {"type": "object", "properties": {}}
    stub.execute = AsyncMock(return_value={"result": "success"})
    return stub


@pytest.fixture
def context(spell: MvgeSpell) -> LoopContext:
    return LoopContext(
        system_prompt="You are a helpful assistant.",
        invocations=[SummonerRequest(role="user", content="Hello")],
        spells=[spell],
        contemplation_level=ContemplationLevel.OFF,
        max_tokens=4096,
        temperature=0.7,
    )


class TestLoopDrivesRealm:
    @pytest.mark.asyncio
    async def test_stream_fn_called_once_for_single_turn(
        self, context: LoopContext
    ) -> None:
        script = TurnScript([[_text()]])

        await run_loop(context, script, Recorder(), LoopCallbacks())

        assert len(script.calls) == 1

    @pytest.mark.asyncio
    async def test_stream_fn_called_again_after_spell_use(
        self, context: LoopContext
    ) -> None:
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, Recorder(), LoopCallbacks())

        assert len(script.calls) == 2

    @pytest.mark.asyncio
    async def test_second_turn_receives_spell_result(
        self, context: LoopContext
    ) -> None:
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, Recorder(), LoopCallbacks())

        second_turn = script.calls[1]
        assert any(isinstance(inv, SpellResultMessage) for inv in second_turn)

    @pytest.mark.asyncio
    async def test_turn_start_emitted_per_turn(self, context: LoopContext) -> None:
        emit = Recorder()
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, emit, LoopCallbacks())

        assert emit.count(MvgeEventType.TURN_START) == 2

    @pytest.mark.asyncio
    async def test_agent_start_emitted_once_across_turns(
        self, context: LoopContext
    ) -> None:
        emit = Recorder()
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, emit, LoopCallbacks())

        assert emit.count(MvgeEventType.AGENT_START) == 1
        assert emit.count(MvgeEventType.AGENT_END) == 1


class TestMaxTurns:
    @pytest.mark.asyncio
    async def test_max_turns_lives_on_context(self) -> None:
        assert LoopContext().max_turns == 50

    @pytest.mark.asyncio
    async def test_raises_when_max_turns_exceeded(self, spell: MvgeSpell) -> None:
        context = LoopContext(
            invocations=[SummonerRequest(role="user", content="Hello")],
            spells=[spell],
            max_turns=3,
        )
        # Always asks for another spell cast, so the loop never settles.
        script = TurnScript([[_spell_call()]])

        with pytest.raises(RuntimeError, match="Max turns exceeded"):
            await run_loop(context, script, Recorder(), LoopCallbacks())


class TestTruncatedSpellCalls:
    @pytest.mark.asyncio
    async def test_truncated_spell_call_is_not_executed(
        self, context: LoopContext, spell: MvgeSpell
    ) -> None:
        # stop_reason LENGTH means arguments may be cut off mid-stream.
        script = TurnScript([[_spell_call(stop=StopReason.LENGTH)]])

        await run_loop(context, script, Recorder(), LoopCallbacks())

        spell.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_truncated_spell_call_yields_error_result(
        self, context: LoopContext
    ) -> None:
        script = TurnScript([[_spell_call(stop=StopReason.LENGTH)]])

        new_invocations = await run_loop(context, script, Recorder(), LoopCallbacks())

        results = [
            inv for inv in new_invocations if isinstance(inv, SpellResultMessage)
        ]
        assert len(results) == 1
        assert results[0].is_error is True
        assert "truncated" in results[0].content[0]["text"].lower()


class TestSteeringAndFollowUp:
    @pytest.mark.asyncio
    async def test_steering_messages_injected_into_next_turn(
        self, context: LoopContext
    ) -> None:
        drained = False

        async def get_steering() -> list[MvgeInvocation]:
            nonlocal drained
            if drained:
                return []
            drained = True
            return [SummonerRequest(role="user", content="steer me")]

        callbacks = LoopCallbacks(get_steering_messages=get_steering)
        script = TurnScript([[_text("First")], [_text("Second")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert len(script.calls) == 2
        contents = [
            inv.content for inv in script.calls[1] if isinstance(inv, SummonerRequest)
        ]
        assert "steer me" in contents

    @pytest.mark.asyncio
    async def test_follow_up_messages_continue_after_stop(
        self, context: LoopContext
    ) -> None:
        drained = False

        async def get_follow_up() -> list[MvgeInvocation]:
            nonlocal drained
            if drained:
                return []
            drained = True
            return [SummonerRequest(role="user", content="follow up")]

        callbacks = LoopCallbacks(get_follow_up_messages=get_follow_up)
        script = TurnScript([[_text("First")], [_text("Second")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert len(script.calls) == 2

    @pytest.mark.asyncio
    async def test_no_extra_turn_when_queues_empty(self, context: LoopContext) -> None:
        async def empty() -> list[MvgeInvocation]:
            return []

        callbacks = LoopCallbacks(
            get_steering_messages=empty, get_follow_up_messages=empty
        )
        script = TurnScript([[_text("Only")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert len(script.calls) == 1


class TestAfterInvocationCallback:
    @pytest.mark.asyncio
    async def test_called_after_each_mvge_invocation(
        self, context: LoopContext
    ) -> None:
        seen: list[list[MvgeInvocation]] = []

        async def after(invocations: list[MvgeInvocation]) -> None:
            seen.append(list(invocations))

        callbacks = LoopCallbacks(after_invocation=after)
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert len(seen) == 2

    @pytest.mark.asyncio
    async def test_replacement_transcript_used_for_next_turn(
        self, context: LoopContext
    ) -> None:
        compacted = [SummonerRequest(role="user", content="compacted history")]

        async def after(invocations: list[MvgeInvocation]) -> list[MvgeInvocation]:
            return list(compacted)

        callbacks = LoopCallbacks(after_invocation=after)
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, Recorder(), callbacks)

        second_turn = script.calls[1]
        assert second_turn == compacted

    @pytest.mark.asyncio
    async def test_none_return_leaves_transcript_untouched(
        self, context: LoopContext
    ) -> None:
        async def after(invocations: list[MvgeInvocation]) -> None:
            return None

        callbacks = LoopCallbacks(after_invocation=after)
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, Recorder(), callbacks)

        second_turn = script.calls[1]
        assert any(isinstance(inv, SpellResultMessage) for inv in second_turn)


class TestCoreStaysDecoupled:
    def test_core_does_not_import_realm(self) -> None:
        import inspect

        from mvgeos_agent.core_loop import run_loop

        source = inspect.getsource(run_loop)
        assert "Realm(" not in source
        assert "realm.stream" not in source
        assert "RuneRunner" not in source
        assert "SigilHook" not in source

    @pytest.mark.asyncio
    async def test_context_invocations_not_mutated_across_turns(
        self, context: LoopContext
    ) -> None:
        before = list(context.invocations)
        script = TurnScript([[_spell_call()], [_text("Done")]])

        await run_loop(context, script, Recorder(), LoopCallbacks())

        assert context.invocations == before


class TestQueueMode:
    @pytest.mark.asyncio
    async def test_default_queue_mode_is_one_at_a_time(self) -> None:
        assert LoopContext().queue_mode == QueueMode.ONE_AT_A_TIME

    @pytest.mark.asyncio
    async def test_all_mode_drains_entire_steer_queue(
        self, context: LoopContext
    ) -> None:
        context = LoopContext(
            invocations=context.invocations,
            spells=context.spells,
            queue_mode=QueueMode.ALL,
        )
        drained = False
        all_staged: list[list[MvgeInvocation]] = []

        async def get_steering() -> list[MvgeInvocation]:
            nonlocal drained
            if drained:
                return []
            drained = True
            staged = [
                SummonerRequest(role="user", content="steer one"),
                SummonerRequest(role="user", content="steer two"),
                SummonerRequest(role="user", content="steer three"),
            ]
            all_staged.append(staged)
            return staged

        callbacks = LoopCallbacks(get_steering_messages=get_steering)
        script = TurnScript([[_text("First")], [_text("Second")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert len(all_staged) == 1
        assert len(all_staged[0]) == 3

    @pytest.mark.asyncio
    async def test_one_at_a_time_drains_single_steer_message(
        self, context: LoopContext
    ) -> None:
        context = LoopContext(
            invocations=context.invocations,
            spells=context.spells,
            queue_mode=QueueMode.ONE_AT_A_TIME,
        )
        steer_queue = [
            SummonerRequest(role="user", content="steer one"),
            SummonerRequest(role="user", content="steer two"),
            SummonerRequest(role="user", content="steer three"),
        ]
        all_drained: list[list[MvgeInvocation]] = []

        async def get_steering() -> list[MvgeInvocation]:
            if not steer_queue:
                return []
            drained = [steer_queue.pop(0)]
            all_drained.append(drained)
            return drained

        callbacks = LoopCallbacks(get_steering_messages=get_steering)
        script = TurnScript(
            [[_text("First")], [_text("Second")], [_text("Third")], [_text("Fourth")]]
        )

        await run_loop(context, script, Recorder(), callbacks)

        assert len(all_drained) <= 4
        for batch in all_drained:
            assert len(batch) == 1

    @pytest.mark.asyncio
    async def test_one_at_a_time_drains_all_staged_messages_over_multiple_turns(
        self, context: LoopContext
    ) -> None:
        context = LoopContext(
            invocations=context.invocations,
            spells=context.spells,
            queue_mode=QueueMode.ONE_AT_A_TIME,
        )
        steer_queue = [
            SummonerRequest(role="user", content="steer one"),
            SummonerRequest(role="user", content="steer two"),
            SummonerRequest(role="user", content="steer three"),
        ]

        async def get_steering() -> list[MvgeInvocation]:
            if not steer_queue:
                return []
            return [steer_queue.pop(0)]

        callbacks = LoopCallbacks(get_steering_messages=get_steering)
        script = TurnScript(
            [
                [_text("First")],
                [_text("Second")],
                [_text("Third")],
                [_text("Fourth")],
            ]
        )

        await run_loop(context, script, Recorder(), callbacks)

        assert len(script.calls) == 4
        assert not steer_queue

    @pytest.mark.asyncio
    async def test_one_at_a_time_drains_single_followup_message(
        self, context: LoopContext
    ) -> None:
        context = LoopContext(
            invocations=context.invocations,
            spells=context.spells,
            queue_mode=QueueMode.ONE_AT_A_TIME,
        )
        followup_queue = [
            SummonerRequest(role="user", content="followup one"),
            SummonerRequest(role="user", content="followup two"),
            SummonerRequest(role="user", content="followup three"),
        ]
        all_drained: list[list[MvgeInvocation]] = []

        async def get_follow_up() -> list[MvgeInvocation]:
            if not followup_queue:
                return []
            drained = [followup_queue.pop(0)]
            all_drained.append(drained)
            return drained

        callbacks = LoopCallbacks(get_follow_up_messages=get_follow_up)
        script = TurnScript(
            [
                [_text("First")],
                [_text("Second")],
                [_text("Third")],
                [_text("Fourth")],
            ]
        )

        await run_loop(context, script, Recorder(), callbacks)

        for batch in all_drained:
            assert len(batch) == 1

    @pytest.mark.asyncio
    async def test_all_mode_drains_multiple_followup_messages(
        self, context: LoopContext
    ) -> None:
        context = LoopContext(
            invocations=context.invocations,
            spells=context.spells,
            queue_mode=QueueMode.ALL,
        )
        drained = False

        async def get_follow_up() -> list[MvgeInvocation]:
            nonlocal drained
            if drained:
                return []
            drained = True
            return [
                SummonerRequest(role="user", content="followup one"),
                SummonerRequest(role="user", content="followup two"),
            ]

        callbacks = LoopCallbacks(get_follow_up_messages=get_follow_up)
        script = TurnScript([[_text("First")], [_text("Second")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert len(script.calls) == 2

    @pytest.mark.asyncio
    async def test_one_at_a_time_preserves_unprocessed_steer_items(
        self, context: LoopContext
    ) -> None:
        context = LoopContext(
            invocations=context.invocations,
            spells=context.spells,
            queue_mode=QueueMode.ONE_AT_A_TIME,
        )
        steer_queue = [
            SummonerRequest(role="user", content="steer one"),
            SummonerRequest(role="user", content="steer two"),
        ]
        drained_items: list[str] = []

        async def get_steering() -> list[MvgeInvocation]:
            if not steer_queue:
                return []
            item = steer_queue.pop(0)
            drained_items.append(item.content or "")
            return [item]

        callbacks = LoopCallbacks(get_steering_messages=get_steering)
        script = TurnScript([[_text("First")], [_text("Second")]])

        await run_loop(context, script, Recorder(), callbacks)

        assert drained_items == ["steer one", "steer two"]


class TestBaseMvgeNoLongerOwnsTurnLoop:
    def test_make_stream_removed(self) -> None:
        from mvgeos_agent.base_mvge import BaseMvge

        assert not hasattr(BaseMvge, "_make_stream")


class TestBaseMvgeQueueMode:
    def test_default_queue_mode_is_one_at_a_time(self) -> None:
        from mvgeos_agent.base_mvge import BaseMvge

        agent = BaseMvge(api_key="test-key")
        assert agent.queue_mode == QueueMode.ONE_AT_A_TIME

    def test_queue_mode_can_be_set_to_all(self) -> None:
        from mvgeos_agent.base_mvge import BaseMvge

        agent = BaseMvge(api_key="test-key")
        agent.queue_mode = QueueMode.ALL
        assert agent.queue_mode == QueueMode.ALL

    def test_queue_mode_accepts_string(self) -> None:
        from mvgeos_agent.base_mvge import BaseMvge

        agent = BaseMvge(api_key="test-key")
        agent.queue_mode = "one-at-a-time"
        assert agent.queue_mode == QueueMode.ONE_AT_A_TIME
        agent.queue_mode = "all"
        assert agent.queue_mode == QueueMode.ALL
