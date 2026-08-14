import pytest

from mvgeos_agent.harness import MvgeHarness
from mvgeos_agent.loop import MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeResponse,
    MvgeState,
    StopReason,
    SummonerRequest,
)


@pytest.mark.asyncio
async def test_full_harness_loop_integration() -> None:
    state = MvgeState(
        system_prompt="Test prompt",
        spells=[],
        invocations=[SummonerRequest(role="user", content="Hello")],
        contemplation_level=ContemplationLevel.MEDIUM,
    )
    loop = MvgeLoop(state)
    harness = MvgeHarness(loop)

    async def mock_stream_fn(invocations, signal=None):
        from mvgeos_provider.types import Model, RealmResponse

        dummy_model = Model(
            id="test-model",
            name="Test Model",
            realm="test",
            base_url="http://localhost",
            api_key="test-key",
        )
        yield RealmResponse(
            model=dummy_model,
            invocation=MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "Hi from mock stream"}],
                stop_reason=StopReason.STOP,
            ),
        )

    response = await harness.run(
        stream_fn=mock_stream_fn,
        model={"id": "test-model"},
    )

    assert isinstance(response, MvgeResponse)
    assert response.content == [{"type": "text", "text": "Hi from mock stream"}]
