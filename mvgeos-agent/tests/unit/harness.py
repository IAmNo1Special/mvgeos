from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_harness import MvgeHarness
from mvgeos_provider.types import Model, RealmResponse

from mvgeos_agent.compaction_runner import CompactionRunner
from mvgeos_agent.loop import LoopCallbacks, LoopContext, MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
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


def _stream(
    responses: list[RealmResponse],
) -> Callable[[list[Any]], AsyncIterator[RealmResponse]]:
    turn = -1

    def stream_fn(invocations: list[Any]) -> AsyncIterator[RealmResponse]:
        nonlocal turn
        turn += 1
        response = responses[min(turn, len(responses) - 1)]

        async def gen() -> AsyncIterator[RealmResponse]:
            yield response

        return gen()

    return stream_fn


def _text_response(text: str = "Hello!") -> RealmResponse:
    return RealmResponse(
        model=_model(),
        invocation=MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": text}],
            stop_reason=StopReason.STOP,
        ),
    )


def _spell_call_response(spell_name: str = "test_spell") -> RealmResponse:
    return RealmResponse(
        model=_model(),
        invocation=MvgeResponse(
            role="assistant",
            content=[
                {
                    "type": "tool_call",
                    "tool_call": {
                        "id": "call-1",
                        "name": spell_name,
                        "arguments": {},
                    },
                }
            ],
            stop_reason=StopReason.SPELL_USE,
        ),
    )


class Recorder:
    """Recording emit sink standing in for the MvgeLoop wrapper."""

    def __init__(self) -> None:
        self.events: list[MvgeEvent] = []

    async def __call__(self, event: MvgeEvent) -> None:
        self.events.append(event)

    def types(self) -> list[MvgeEventType]:
        return [event.type for event in self.events]

    def of_type(self, event_type: MvgeEventType) -> list[MvgeEvent]:
        return [event for event in self.events if event.type == event_type]


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


@pytest.fixture
def mock_loop(spell: MvgeSpell) -> MvgeLoop:
    """Create a real MvgeLoop with mocked state for testing."""
    state = MagicMock()
    state.is_streaming = False
    state.model = {}
    state.system_prompt = "test"
    state.invocations = [SummonerRequest(role="user", content="Hello")]
    state.max_tokens = 4096
    state.temperature = 0.7
    state.spell_timeout_ms = 30000
    state.contemplation_budget = None
    state.exclude_contemplation = False
    state.max_turns = 50
    state.contemplation_level = ContemplationLevel.OFF
    state.spells = [spell]
    state.rune_runner = None
    state.steer_queue = []
    state.followup_queue = []
    state.agent_session = None
    state.event_bus = None

    loop = MvgeLoop(state)
    # Mock the internal _emit method instead of the property
    loop._emit = AsyncMock()
    return loop


@pytest.fixture
def mock_compaction() -> CompactionRunner:
    compaction = MagicMock(spec=CompactionRunner)
    compaction.maybe_compact = AsyncMock(return_value=None)
    return compaction


@pytest.fixture
def callbacks() -> LoopCallbacks:
    return LoopCallbacks()


class TestMvgeHarness:
    @pytest.mark.asyncio
    async def test_harness_runs_session(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_text_response()])

        result = await harness.run(stream_fn, {"id": "test-model"}, "none")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP
        mock_loop.emit.assert_called()

    @pytest.mark.asyncio
    async def test_should_stop_after_turn_stops_early(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
    ) -> None:
        stop_after_turn = AsyncMock(return_value=True)
        callbacks = LoopCallbacks(should_stop_after_turn=stop_after_turn)

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_spell_call_response(), _text_response("Turn 2")])

        result = await harness.run(stream_fn, {"id": "test-model"}, "none")

        # Should stop after first turn
        assert stop_after_turn.call_count == 1
        assert isinstance(result, MvgeResponse)

    @pytest.mark.asyncio
    async def test_prepare_next_turn_modifies_context(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
    ) -> None:
        new_context = LoopContext(
            system_prompt="Modified prompt",
            invocations=[SummonerRequest(role="user", content="Modified")],
            spells=[],
            contemplation_level=ContemplationLevel.OFF,
            max_tokens=4096,
            temperature=0.7,
        )
        prepare_next_turn = AsyncMock(return_value=new_context)
        callbacks = LoopCallbacks(prepare_next_turn=prepare_next_turn)

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_spell_call_response(), _text_response("Done")])

        await harness.run(stream_fn, {"id": "test-model"}, "none")

        # prepare_next_turn should be called before second turn
        assert prepare_next_turn.call_count == 1

    @pytest.mark.asyncio
    async def test_compaction_runs_after_invocation(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_text_response()])

        await harness.run(stream_fn, {"id": "test-model"}, "none")

        # Compaction should be called after each invocation
        mock_compaction.maybe_compact.assert_called()

    @pytest.mark.asyncio
    async def test_steering_queue_drains_between_turns(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
    ) -> None:
        steering_messages = [SummonerRequest(role="user", content="Steer")]
        call_count = 0

        async def get_steering() -> list[MvgeInvocation]:
            nonlocal call_count
            call_count += 1
            # Return messages only on first call, then empty (simulating drained queue)
            if call_count == 1:
                return steering_messages
            return []

        callbacks = LoopCallbacks(get_steering_messages=get_steering)

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_spell_call_response(), _text_response("Done")])

        await harness.run(stream_fn, {"id": "test-model"}, "none")

        # Steering is drained at least once between turns
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_follow_up_queue_continues_outer_loop(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
    ) -> None:
        follow_up_messages = [SummonerRequest(role="user", content="Follow up")]
        get_follow_up = AsyncMock(side_effect=[follow_up_messages, []])
        callbacks = LoopCallbacks(get_follow_up_messages=get_follow_up)

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_spell_call_response(), _text_response("Done")])

        await harness.run(stream_fn, {"id": "test-model"}, "none")

        # Follow-up should be drained and cause outer loop to continue
        assert get_follow_up.call_count >= 1

    @pytest.mark.asyncio
    async def test_harness_returns_final_invocation(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _stream([_text_response("Final")])

        result = await harness.run(stream_fn, {"id": "test-model"}, "none")

        assert isinstance(result, MvgeResponse)
        assert result.content[0]["text"] == "Final"
