from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_provider.types import Model, RealmResponse

from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    StopReason,
    SummonerRequest,
)


class TestMvgeLoop:
    @pytest.fixture
    def mock_spell(self) -> MvgeSpell:
        spell = MagicMock(spec=MvgeSpell)
        spell.name = "test_spell"
        spell.description = "A test spell"
        spell.parameters = {"type": "object", "properties": {}}
        spell.execute = AsyncMock(return_value={"result": "success"})
        return spell

    @pytest.fixture
    def state(self, mock_spell: MvgeSpell) -> MvgeState:
        return MvgeState(
            system_prompt="You are a helpful assistant.",
            model={"id": "test-model", "name": "Test Model"},
            contemplation_level=ContemplationLevel.OFF,
            spells=[mock_spell],
            invocations=[
                SummonerRequest(role="user", content="Hello"),
            ],
            mana_budget=1000,
            max_tokens=4096,
            temperature=0.7,
        )

    def _make_realm_stream(
        self, responses: list[RealmResponse]
    ) -> AsyncIterator[RealmResponse]:
        async def gen() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        return gen()

    @pytest.mark.asyncio
    async def test_loop_single_turn_no_spells(self, state: MvgeState) -> None:
        from mvgeos_agent.loop import MvgeLoop

        model_obj = Model(
            id="test-model",
            name="Test Model",
            realm="test",
            provider="test",
            base_url="https://api.test.com",
            api_key="test",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello!"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]
        stream_fn = self._make_realm_stream(responses)

        loop = MvgeLoop(state)
        result = await loop.run(stream_fn, {"id": "test-model"}, "off")

        assert isinstance(result, MvgeResponse)
        assert result.content == [{"type": "text", "text": "Hello!"}]
        assert result.stop_reason == StopReason.STOP
        assert len(state.invocations) == 2

    @pytest.mark.asyncio
    async def test_loop_with_spell_cast(
        self, state: MvgeState, mock_spell: MvgeSpell
    ) -> None:
        from mvgeos_agent.loop import MvgeLoop

        model_obj = Model(
            id="test-model",
            name="Test Model",
            realm="test",
            provider="test",
            base_url="https://api.test.com",
            api_key="test",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[
                        {
                            "type": "tool_call",
                            "tool_call": {
                                "id": "call-1",
                                "name": "test_spell",
                                "arguments": {},
                            },
                        }
                    ],
                    stop_reason=StopReason.SPELL_USE,
                ),
            ),
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Spell executed successfully"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]
        stream_fn = self._make_realm_stream(responses)

        loop = MvgeLoop(state)
        result = await loop.run(stream_fn, {"id": "test-model"}, "off")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP
        mock_spell.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_loop_mana_exhaustion(self, state: MvgeState) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state.mana_budget = 10

        model_obj = Model(
            id="test-model",
            name="Test Model",
            realm="test",
            provider="test",
            base_url="https://api.test.com",
            api_key="test",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "This uses a lot of mana"}],
                    stop_reason=StopReason.LENGTH,
                    mana_usage={"input": 15, "output": 5},
                ),
            ),
        ]
        stream_fn = self._make_realm_stream(responses)

        loop = MvgeLoop(state)
        result = await loop.run(stream_fn, {"id": "test-model"}, "off")

        assert result.stop_reason == StopReason.LENGTH

    @pytest.mark.asyncio
    async def test_loop_error_handling(self, state: MvgeState) -> None:
        from mvgeos_agent.loop import MvgeLoop

        async def error_stream_gen() -> AsyncIterator[RealmResponse]:
            raise RuntimeError("API error")
            yield  # Never reached

        loop = MvgeLoop(state)
        with pytest.raises(RuntimeError, match="API error"):
            await loop.run(error_stream_gen(), {"id": "test-model"}, "off")

    @pytest.mark.asyncio
    async def test_loop_no_initial_invocation(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(system_prompt="test")

        async def empty_stream() -> AsyncIterator[RealmResponse]:
            if False:
                yield

        stream_fn = empty_stream()

        loop = MvgeLoop(state)
        with pytest.raises(RuntimeError, match="No invocations to process"):
            await loop.run(stream_fn, {"id": "test-model"}, "off")
