from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_provider.types import Model, RealmResponse
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook

from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    SpellResultMessage,
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
        result = await loop.run(stream_fn, {"id": "test-model"}, "none")

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
        result = await loop.run(stream_fn, {"id": "test-model"}, "none")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP
        mock_spell.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_loop_spell_timeout(
        self, state: MvgeState, mock_spell: MvgeSpell
    ) -> None:
        from mvgeos_agent.loop import MvgeLoop

        async def slow_execute(*args: Any, **kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {}

        mock_spell.execute = slow_execute  # type: ignore[method-assign]
        state.spell_timeout_ms = 100

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
                    content=[{"type": "text", "text": "Done"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]
        stream_fn = self._make_realm_stream(responses)

        loop = MvgeLoop(state)
        result = await loop.run(stream_fn, {"id": "test-model"}, "none")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP

        spell_results = [
            inv for inv in state.invocations if isinstance(inv, SpellResultMessage)
        ]
        timeout_result = next((r for r in spell_results if r.is_error), None)
        assert timeout_result is not None
        assert "timed out" in timeout_result.content[0]["text"]
        assert "test_spell" in timeout_result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_loop_persists_spell_use_invocation(self, state: MvgeState) -> None:
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
                    content=[{"type": "text", "text": "Done"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]
        stream_fn = self._make_realm_stream(responses)

        loop = MvgeLoop(state)
        await loop.run(stream_fn, {"id": "test-model"}, "none")

        tool_call_msgs = [
            inv
            for inv in state.invocations
            if isinstance(inv, MvgeResponse)
            and inv.content
            and inv.content[0].get("type") == "tool_call"
        ]
        assert len(tool_call_msgs) == 1
        assert tool_call_msgs[0].stop_reason == StopReason.SPELL_USE

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
        result = await loop.run(stream_fn, {"id": "test-model"}, "none")

        assert result.stop_reason == StopReason.LENGTH

    @pytest.mark.asyncio
    async def test_loop_error_handling(self, state: MvgeState) -> None:
        from mvgeos_agent.loop import MvgeLoop

        async def error_stream_gen() -> AsyncIterator[RealmResponse]:
            raise RuntimeError("API error")
            yield  # Never reached

        loop = MvgeLoop(state)
        with pytest.raises(RuntimeError, match="API error"):
            await loop.run(error_stream_gen(), {"id": "test-model"}, "none")

    @pytest.mark.asyncio
    async def test_loop_raises_rate_limit_error(self, state: MvgeState) -> None:
        from mvgeos_agent.errors import RateLimitError
        from mvgeos_agent.loop import MvgeLoop

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )

        async def rate_limit_stream() -> AsyncIterator[RealmResponse]:
            yield RealmResponse(
                model=model_obj,
                error_message="You are being rate limited",
                error_code="rate_limited",
            )

        loop = MvgeLoop(state)
        with pytest.raises(RateLimitError, match="rate limited"):
            await loop.run(rate_limit_stream(), {"id": "test-model"}, "none")

    @pytest.mark.asyncio
    async def test_loop_raises_auth_error(self, state: MvgeState) -> None:
        from mvgeos_agent.errors import AuthenticationError
        from mvgeos_agent.loop import MvgeLoop

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )

        async def auth_stream() -> AsyncIterator[RealmResponse]:
            yield RealmResponse(
                model=model_obj,
                error_message="User not found",
                error_code="auth_failed",
            )

        loop = MvgeLoop(state)
        with pytest.raises(AuthenticationError, match="User not found"):
            await loop.run(auth_stream(), {"id": "test-model"}, "none")

    @pytest.mark.asyncio
    async def test_loop_generic_provider_error_stays_runtime_error(
        self, state: MvgeState
    ) -> None:
        from mvgeos_agent.loop import MvgeLoop

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )

        async def bad_request_stream() -> AsyncIterator[RealmResponse]:
            yield RealmResponse(
                model=model_obj,
                error_message="Bad request",
                error_code=None,
            )

        loop = MvgeLoop(state)
        with pytest.raises(RuntimeError, match="Bad request"):
            await loop.run(bad_request_stream(), {"id": "test-model"}, "none")

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
            await loop.run(stream_fn, {"id": "test-model"}, "none")


class TestMvgeLoopProviderHooks:
    @pytest.mark.asyncio
    async def test_before_provider_request_is_emitted(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model", "name": "Test"},
            invocations=[SummonerRequest(role="user", content="hi")],
        )
        runner = RuneRunner()
        handler = MagicMock()
        runner.register_handler(SigilHook.BEFORE_PROVIDER_REQUEST, handler)
        state.rune_runner = runner

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]

        async def stream() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        loop = MvgeLoop(state)
        await loop.run(stream(), {"id": "test-model"}, "none")
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_after_provider_response_is_emitted(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model", "name": "Test"},
            invocations=[SummonerRequest(role="user", content="hi")],
        )
        runner = RuneRunner()
        handler = MagicMock()
        runner.register_handler(SigilHook.AFTER_PROVIDER_RESPONSE, handler)
        state.rune_runner = runner

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]

        async def stream() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        loop = MvgeLoop(state)
        await loop.run(stream(), {"id": "test-model"}, "none")
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_provider_headers_chain_applies_headers(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model", "name": "Test"},
            invocations=[SummonerRequest(role="user", content="hi")],
        )
        runner = RuneRunner()

        def add_header(data: dict) -> dict:
            data["X-Custom"] = "value"
            return data

        runner.register_handler(SigilHook.BEFORE_PROVIDER_HEADERS, add_header)
        state.rune_runner = runner

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]

        async def stream() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        loop = MvgeLoop(state)
        await loop.run(stream(), {"id": "test-model"}, "none")

        assert "headers" in state.model
        assert state.model["headers"].get("X-Custom") == "value"

    @pytest.mark.asyncio
    async def test_provider_hooks_error_propagates(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model", "name": "Test"},
            invocations=[SummonerRequest(role="user", content="hi")],
        )
        runner = RuneRunner()

        def bad_handler(data: dict) -> None:
            raise ValueError("oops")

        runner.register_handler(SigilHook.BEFORE_PROVIDER_REQUEST, bad_handler)
        state.rune_runner = runner

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]

        async def stream() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        loop = MvgeLoop(state)
        with pytest.raises(ValueError, match="oops"):
            await loop.run(stream(), {"id": "test-model"}, "none")


class TestMvgeLoopContextTransform:
    @pytest.mark.asyncio
    async def test_context_transform_modifies_invocations(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model", "name": "Test"},
            invocations=[SummonerRequest(role="user", content="original")],
        )
        runner = RuneRunner()

        def transform(invocations: list) -> list:
            invocations[0].content = "transformed"
            return invocations

        runner.register_handler(SigilHook.CONTEXT_TRANSFORM, transform)
        state.rune_runner = runner

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]

        async def stream() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        loop = MvgeLoop(state)
        await loop.run(stream(), {"id": "test-model"}, "none")

        assert state.invocations[0].content == "transformed"


class TestMvgeLoopInputHook:
    @pytest.mark.asyncio
    async def test_input_hook_emitted_for_summoner_request(self) -> None:
        from mvgeos_agent.loop import MvgeLoop

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model", "name": "Test"},
            invocations=[SummonerRequest(role="user", content="my input")],
        )
        runner = RuneRunner()
        handler = MagicMock()
        runner.register_handler(SigilHook.INPUT, handler)
        state.rune_runner = runner

        model_obj = Model(
            id="test-model",
            name="Test",
            realm="test",
            provider="test",
            base_url="",
            api_key="",
        )
        responses = [
            RealmResponse(
                model=model_obj,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]

        async def stream() -> AsyncIterator[RealmResponse]:
            for r in responses:
                yield r

        loop = MvgeLoop(state)
        await loop.run(stream(), {"id": "test-model"}, "none")

        handler.assert_called_once()
        call_data = handler.call_args[0][0]
        assert call_data["content"] == "my input"


class TestMvgeLoopSessionHooks:
    @pytest.mark.asyncio
    async def test_session_start_emitted_when_agent_session_in_state(
        self,
    ) -> None:
        from mvgeos_tome.ledger import TomeLedger

        from mvgeos_agent.agent_session import MvgeTome
        from mvgeos_agent.loop import MvgeLoop

        with tempfile.TemporaryDirectory() as tmp:
            ledger = TomeLedger(Path(tmp))
            meta = ledger.create_tome("/tmp")
            runner = RuneRunner()
            handler = MagicMock()
            runner.register_handler(SigilHook.SESSION_START, handler)

            session = MvgeTome(ledger, meta, runner)
            state = MvgeState(
                system_prompt="test",
                model={"id": "test-model", "name": "Test"},
                invocations=[SummonerRequest(role="user", content="hi")],
                rune_runner=runner,
                agent_session=session,
            )

            model_obj = Model(
                id="test-model",
                name="Test",
                realm="test",
                provider="test",
                base_url="",
                api_key="",
            )
            responses = [
                RealmResponse(
                    model=model_obj,
                    invocation=MvgeResponse(
                        role="assistant",
                        content=[{"type": "text", "text": "Hello"}],
                        stop_reason=StopReason.STOP,
                    ),
                ),
            ]

            async def stream() -> AsyncIterator[RealmResponse]:
                for r in responses:
                    yield r

            loop = MvgeLoop(state)
            await session.start()
            await loop.run(stream(), {"id": "test-model"}, "none")

            handler.assert_called_once()
            call_data = handler.call_args[0][0]
            assert call_data["reason"] == "startup"

    @pytest.mark.asyncio
    async def test_session_shutdown_emitted_when_agent_session_in_state(
        self,
    ) -> None:
        from mvgeos_tome.ledger import TomeLedger

        from mvgeos_agent.agent_session import MvgeTome
        from mvgeos_agent.loop import MvgeLoop

        with tempfile.TemporaryDirectory() as tmp:
            ledger = TomeLedger(Path(tmp))
            meta = ledger.create_tome("/tmp")
            runner = RuneRunner()
            handler = MagicMock()
            runner.register_handler(SigilHook.SESSION_SHUTDOWN, handler)

            session = MvgeTome(ledger, meta, runner)
            state = MvgeState(
                system_prompt="test",
                model={"id": "test-model", "name": "Test"},
                invocations=[SummonerRequest(role="user", content="hi")],
                rune_runner=runner,
                agent_session=session,
            )

            model_obj = Model(
                id="test-model",
                name="Test",
                realm="test",
                provider="test",
                base_url="",
                api_key="",
            )
            responses = [
                RealmResponse(
                    model=model_obj,
                    invocation=MvgeResponse(
                        role="assistant",
                        content=[{"type": "text", "text": "Hello"}],
                        stop_reason=StopReason.STOP,
                    ),
                ),
            ]

            async def stream() -> AsyncIterator[RealmResponse]:
                for r in responses:
                    yield r

            loop = MvgeLoop(state)
            await session.start()
            await loop.run(stream(), {"id": "test-model"}, "none")
            await session.shutdown()

            handler.assert_called_once()
