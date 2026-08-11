from unittest.mock import AsyncMock, MagicMock

import pytest

from mvgeos_agent.harness import MvgeHarness
from mvgeos_agent.loop import LoopCallbacks, MvgeLoop
from mvgeos_agent.types import (
    MvgeResponse,
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
    mock_compaction.maybe_compact.assert_awaited_once_with(invocations)
