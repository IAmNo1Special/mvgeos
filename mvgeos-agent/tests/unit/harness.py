from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_core.channel import (
    Model,
    MvgeResponse,
    StopReason,
)
from mvgeos_core.invocations import (
    MvgeInvocation,
    SummonerRequest,
)
from mvgeos_core.loop import LoopCallbacks

from mvgeos_agent.harness import MvgeHarness
from mvgeos_agent.harness.compaction.compaction import DEFAULT_COMPACTION_SETTINGS
from mvgeos_agent.mvge_loop import MvgeLoop
from mvgeos_agent.types import MvgeState


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
    mock_loop._build_callbacks.return_value = LoopCallbacks()
    mock_loop.set_after_invocation = MagicMock()

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

    # Verify set_after_invocation was called
    mock_loop.set_after_invocation.assert_called_once()
    after_invocation_callback = mock_loop.set_after_invocation.call_args[0][0]

    invocations = [SummonerRequest(role="user", content="Test")]
    res = await after_invocation_callback(invocations)
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


def _crowded_model() -> Model:
    return Model(
        id="test-provider/test-model",
        name="Test Model",
        realm="test-realm",
        base_url="https://api.example.com/v1",
        api_key="test-key",
        context_window=100_000,
    )


def _harness_with_compaction(
    invocations: list[MvgeInvocation], model: Model | None = None
) -> tuple[MvgeHarness, MagicMock, MagicMock]:
    mock_loop = MagicMock(spec=MvgeLoop)
    mock_loop._build_callbacks.return_value = LoopCallbacks()
    mock_loop.run = AsyncMock(return_value=MvgeResponse(role="assistant", content=[]))
    mock_state = MagicMock(spec=MvgeState)
    mock_state.invocations = list(invocations)
    mock_compaction = MagicMock()
    mock_compaction._settings = DEFAULT_COMPACTION_SETTINGS
    mock_compaction.force_compact = AsyncMock(return_value=None)
    harness = MvgeHarness(
        loop=mock_loop,
        compaction=mock_compaction,
        state=mock_state,
        model=model or _crowded_model(),
    )
    return harness, mock_compaction, mock_state


@pytest.mark.asyncio
async def test_harness_precompact_when_pool_crowded() -> None:
    crowded = [
        MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "prior"}],
            mana_usage={"total": 90_000.0},
            stop_reason=StopReason.STOP,
        )
    ]
    compacted = [SummonerRequest(role="user", content="summary")]
    harness, mock_compaction, mock_state = _harness_with_compaction(crowded)
    mock_compaction.force_compact = AsyncMock(return_value=compacted)

    await harness.run(stream_fn=AsyncMock(), model={"id": "test-model"})

    mock_compaction.force_compact.assert_awaited_once()
    assert mock_state.invocations == compacted


@pytest.mark.asyncio
async def test_harness_no_precompact_when_room() -> None:
    roomy = [
        MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "prior"}],
            mana_usage={"total": 100.0},
            stop_reason=StopReason.STOP,
        )
    ]
    harness, mock_compaction, _ = _harness_with_compaction(roomy)

    await harness.run(stream_fn=AsyncMock(), model={"id": "test-model"})

    mock_compaction.force_compact.assert_not_awaited()


@pytest.mark.asyncio
async def test_harness_no_precompact_without_window() -> None:
    crowded = [
        MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "prior"}],
            mana_usage={"total": 90_000.0},
            stop_reason=StopReason.STOP,
        )
    ]
    windowless = _crowded_model()
    windowless.context_window = 0
    harness, mock_compaction, _ = _harness_with_compaction(crowded, windowless)

    await harness.run(stream_fn=AsyncMock(), model={"id": "test-model"})

    mock_compaction.force_compact.assert_not_awaited()


@pytest.mark.asyncio
async def test_harness_precompact_failure_does_not_fail_run() -> None:
    crowded = [
        MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "prior"}],
            mana_usage={"total": 90_000.0},
            stop_reason=StopReason.STOP,
        )
    ]
    harness, mock_compaction, mock_state = _harness_with_compaction(crowded)
    mock_compaction.force_compact = AsyncMock(side_effect=RuntimeError("boom"))

    result = await harness.run(stream_fn=AsyncMock(), model={"id": "test-model"})

    assert result is not None
    assert mock_state.invocations == crowded
