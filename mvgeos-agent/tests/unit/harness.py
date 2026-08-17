from unittest.mock import AsyncMock, MagicMock

import pytest

from mvgeos_agent.harness import MvgeHarness
from mvgeos_agent.loop import LoopCallbacks, MvgeLoop
from mvgeos_agent.types import (
    MvgeResponse,
    MvgeState,
    StopReason,
    SummonerRequest,
)


@pytest.mark.asyncio
async def test_harness_delegates_to_loop() -> None:
    mock_loop = MagicMock(spec=MvgeLoop)
    mock_loop._build_callbacks.return_value = LoopCallbacks()
    expected_response = MvgeResponse(
        role="assistant",
        content=[{"type": "text", "text": "Hello user"}],
        stop_reason=StopReason.STOP,
    )
    mock_loop.run = AsyncMock(return_value=expected_response)

    harness = MvgeHarness(mock_loop)
    stream_fn = AsyncMock()

    result = await harness.run(
        stream_fn=stream_fn,
        model={"id": "test-model"},
        contemplation_level="low",
    )

    assert result == expected_response
    mock_loop.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_harness_runs_compaction_callback() -> None:
    mock_loop = MagicMock(spec=MvgeLoop)
    base_callbacks = LoopCallbacks()
    mock_loop._build_callbacks.return_value = base_callbacks

    mock_compaction = AsyncMock()
    mock_compaction.maybe_compact.return_value = [
        SummonerRequest(role="user", content="Compact summary")
    ]

    harness = MvgeHarness(mock_loop, compaction=mock_compaction)
    stream_fn = AsyncMock()

    await harness.run(
        stream_fn=stream_fn,
        model={"id": "test-model"},
    )

    call_args = mock_loop.run.call_args
    assert call_args is not None
    callbacks = call_args.kwargs.get("callbacks")
    assert callbacks is not None
    assert callbacks.after_invocation is not None

    invocations = [SummonerRequest(role="user", content="Test")]
    res = await callbacks.after_invocation(invocations)
    assert res == [SummonerRequest(role="user", content="Compact summary")]
    mock_compaction.maybe_compact.assert_awaited_once_with(invocations, None)


@pytest.mark.asyncio
async def test_harness_state_initialization_and_properties() -> None:
    mock_state = MagicMock(spec=MvgeState)
    mock_tome = MagicMock()
    mock_state.agent_tome = mock_tome
    mock_state.invocations = []

    harness = MvgeHarness(state=mock_state, tome=mock_tome)

    assert harness.state == mock_state
    assert harness.tome == mock_tome
    assert harness.loop is not None
    assert harness.compaction is None


@pytest.mark.asyncio
async def test_harness_switch_tome() -> None:
    mock_state = MagicMock(spec=MvgeState)
    tome1 = MagicMock()
    tome2 = MagicMock()

    harness = MvgeHarness(state=mock_state, tome=tome1)
    assert harness.tome == tome1

    harness.switch_tome(tome2)
    assert harness.tome == tome2
    assert mock_state.agent_tome == tome2


@pytest.mark.asyncio
async def test_harness_set_model_and_realm() -> None:
    mock_state = MagicMock(spec=MvgeState)
    tome = MagicMock()
    mock_realm = MagicMock()
    mock_model = MagicMock()

    harness = MvgeHarness(state=mock_state, tome=tome)
    assert harness.compaction is None

    harness.set_model_and_realm(mock_model, mock_realm)
    assert harness.compaction is not None


@pytest.mark.asyncio
async def test_harness_run_with_prompt_appends_invocation() -> None:
    mock_state = MagicMock(spec=MvgeState)
    mock_state.invocations = []

    mock_loop = MagicMock(spec=MvgeLoop)
    mock_loop._build_callbacks.return_value = LoopCallbacks()
    mock_loop.run = AsyncMock(return_value=MvgeResponse(role="assistant", content=[]))

    harness = MvgeHarness(loop=mock_loop, state=mock_state)
    await harness.run(
        stream_fn=AsyncMock(),
        model={"id": "test-model"},
        prompt="User question",
    )

    assert len(mock_state.invocations) == 1
    assert isinstance(mock_state.invocations[0], SummonerRequest)
    assert mock_state.invocations[0].content == "User question"
