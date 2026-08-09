from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_agent.compaction_runner import CompactionRunner
from mvgeos_agent.loop import LoopCallbacks, LoopContext, MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeResponse,
    MvgeSpell,
    StopReason,
    SummonerRequest,
)
from mvgeos_provider.types import Model, RealmResponse

from mvgeos_harness import MvgeHarness


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
    # Mock the internal _emit method
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


def _make_stream_fn(
    response: RealmResponse,
) -> Callable[[list[Any]], AsyncIterator[RealmResponse]]:
    """Create a stream_fn that yields the given response."""

    def stream_fn(invocations: list[Any]) -> AsyncIterator[RealmResponse]:
        async def gen() -> AsyncIterator[RealmResponse]:
            yield response

        return gen()

    return stream_fn


class TestMvgeHarness:
    @pytest.mark.asyncio
    async def test_harness_delegates_to_loop(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        """Test that harness delegates to MvgeLoop.run()."""
        # Mock the run method for this test
        mock_loop.run = AsyncMock(
            return_value=MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "Done"}],
                stop_reason=StopReason.STOP,
            )
        )

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _make_stream_fn(_text_response())

        result = await harness.run(stream_fn, {"id": "test-model"}, "none")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP
        mock_loop.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_harness_returns_loop_result(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        """Test that harness returns the result from MvgeLoop.run()."""
        final_response = MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "Final"}],
            stop_reason=StopReason.STOP,
        )
        mock_loop.run = AsyncMock(return_value=final_response)

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _make_stream_fn(_text_response())

        result = await harness.run(stream_fn, {"id": "test-model"}, "none")

        assert result is final_response

    @pytest.mark.asyncio
    async def test_harness_passes_parameters_to_loop(
        self,
        mock_loop: MvgeLoop,
        mock_compaction: CompactionRunner,
        callbacks: LoopCallbacks,
    ) -> None:
        """Test that harness passes parameters to loop.run()."""
        mock_loop.run = AsyncMock(
            return_value=MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "Done"}],
                stop_reason=StopReason.STOP,
            )
        )

        harness = MvgeHarness(mock_loop, mock_compaction, callbacks)
        stream_fn = _make_stream_fn(_text_response())

        await harness.run(stream_fn, {"id": "test-model"}, "high")

        mock_loop.run.assert_called_once()
        call_kwargs = mock_loop.run.call_args.kwargs
        assert call_kwargs["stream_fn"] is stream_fn
        assert call_kwargs["model"] == {"id": "test-model"}
        assert call_kwargs["contemplation_level"] == "high"

    @pytest.mark.asyncio
    async def test_harness_uses_loop_callbacks(
        self,
        mock_loop: MvgeLoop,
    ) -> None:
        """Test that harness uses callbacks from loop._build_callbacks()."""
        # The harness calls loop.run() which internally calls _build_callbacks
        # We need to mock _build_callbacks to track if it's called
        original_build_callbacks = mock_loop._build_callbacks
        call_count = 0

        def tracking_build_callbacks() -> LoopCallbacks:
            nonlocal call_count
            call_count += 1
            return original_build_callbacks()

        mock_loop._build_callbacks = tracking_build_callbacks

        harness = MvgeHarness(
            mock_loop, MagicMock(spec=CompactionRunner), LoopCallbacks()
        )
        stream_fn = _make_stream_fn(_text_response())

        await harness.run(stream_fn, {"id": "test-model"}, "none")

        # Verify the loop's _build_callbacks was called by loop.run()
        assert call_count >= 1
