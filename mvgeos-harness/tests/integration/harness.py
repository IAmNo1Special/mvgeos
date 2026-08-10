from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.compaction import CompactionSettings
from mvgeos_agent.compaction_runner import CompactionRunner
from mvgeos_agent.loop import LoopCallbacks, MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    StopReason,
)
from mvgeos_provider.base import Realm
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.loader import load_runes_from_paths
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext, RuneScope
from mvgeos_tome.ledger import TomeLedger

from mvgeos_harness import MvgeHarness


def _model() -> Model:
    return Model(
        id="test/mock-model",
        name="Test Mock Model",
        realm="test",
        base_url="https://api.test.com",
        api_key="test-key",
        context_window=100000,
        max_tokens=4096,
    )


class MockRealm(Realm):
    """A mock Realm that yields pre-configured responses per turn."""

    def __init__(self, responses: list[list[RealmResponse]]) -> None:
        self._response_sets = responses
        self._turn = 0
        self.stream_calls = 0
        self.complete_calls: list[list[dict[str, str]]] = []

    async def stream(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
    ) -> AsyncIterator[RealmResponse]:
        self.stream_calls += 1
        if self._turn < len(self._response_sets):
            responses = self._response_sets[self._turn]
        else:
            responses = self._response_sets[-1]
        self._turn += 1
        for response in responses:
            yield response

    async def complete(
        self,
        model: Model,
        messages: list[dict[str, Any]],
        config: ChannelConfig,
    ) -> RealmResponse:
        self.complete_calls.append(
            [
                {"role": m.get("role", ""), "content": m.get("content", "")}
                for m in messages
            ]
        )
        return RealmResponse(
            model=model,
            invocation=MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "Summary of conversation."}],
                stop_reason=StopReason.STOP,
            ),
            mana_used=10,
            stop_reason=StopReason.STOP.value,
        )

    async def close(self) -> None:
        pass


def _text_response(text: str = "Hello!", mana_used: int = 100) -> RealmResponse:
    return RealmResponse(
        model=_model(),
        invocation=MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": text}],
            stop_reason=StopReason.STOP,
            mana_usage={
                "input": mana_used // 2,
                "output": mana_used // 2,
                "total": mana_used,
            },
        ),
        mana_used=mana_used,
        stop_reason=StopReason.STOP.value,
    )


def _spell_response(spell_name: str = "test_spell") -> RealmResponse:
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
        mana_used=50,
        stop_reason=StopReason.SPELL_USE.value,
    )


class _TestSpell(MvgeSpell):
    def __init__(self) -> None:
        super().__init__(
            name="test_spell",
            description="A test spell",
            parameters={"type": "object", "properties": {}},
        )

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return {"result": "success"}


class _MockMvge(BaseMvge):
    """Concrete BaseMvge subclass that uses a MockRealm."""

    def __init__(self, mock_realm: MockRealm, **kwargs: Any) -> None:
        super().__init__(
            api_key="test-key",
            model="test/mock-model",
            **kwargs,
        )
        self._mock_realm = mock_realm

    def _build_spells(self) -> list[MvgeSpell]:
        return [_TestSpell()]

    def _build_system_prompt(self) -> str:
        return "You are a test assistant."

    async def _build_system_prompt_async(self) -> str:
        return self._build_system_prompt()

    def _compose_model(self, model_id: str) -> Model:
        """Return a test model directly, bypassing the registry."""
        return _model()

    async def initialize(self) -> None:
        """Override to use mock realm instead of creating one from registry."""
        if self._initialized:
            return

        paths_with_scope = [(p, RuneScope.PROJECT) for p in self._runes_paths]
        loads, diagnostics = load_runes_from_paths(paths_with_scope, self._name)
        if loads:
            self._runner = RuneRunner()
            self._runner.bind_context(
                RuneContext(
                    cwd=str(Path.cwd()),
                    mode="cli",
                    agent_name=self._name,
                    api_key=self._api_key,
                )
            )
            await self._runner.load_rune_loads(loads, diagnostics)

        self._model = self._compose_model(self._model_id)

        # Use mock realm instead of creating one from registry
        self._realm = self._mock_realm

        self._tome_ledger = TomeLedger(self._session_dir)

        base_prompt = await self._build_system_prompt_async()

        self._agent_session = None
        if self._tome_ledger is not None:
            meta = self._tome_ledger.create_tome(str(Path.cwd()))
            self._agent_session = MvgeTome(self._tome_ledger, meta, self._runner)
            await self._agent_session.start(reason="startup")

        self._state = MvgeState(
            system_prompt=base_prompt,
            model={"id": self._model_id},
            contemplation_level=ContemplationLevel(self._contemplation_level),
            spells=self._build_spells(),
            invocations=[],
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            contemplation_budget=self._contemplation_budget,
            exclude_contemplation=self._exclude_contemplation,
            rune_runner=self._runner,
            agent_session=self._agent_session,
            event_bus=self._event_bus,
        )

        self._loop = MvgeLoop(self._state)

        self._compaction = CompactionRunner(
            realm=self._realm,
            model=self._model,
            emit=self._loop.emit,
            settings=self._compaction_settings,
            tome=self._agent_session,
        )

        async def after_invocation_with_compaction(
            invocations: list[Any],
        ) -> list[Any] | None:
            if self._compaction is not None:
                replacement = await self._compaction.maybe_compact(list(invocations))
                if replacement is not None:
                    invocations = list(replacement)
            return invocations

        self._loop.set_after_invocation(after_invocation_with_compaction)
        self._harness = MvgeHarness(self._loop, self._compaction, LoopCallbacks())

        self._initialized = True


@pytest.fixture
def temp_session_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


class TestHarnessIntegration:
    @pytest.mark.asyncio
    async def test_full_harness_run_emits_lifecycle_events(
        self, temp_session_dir: Path
    ) -> None:
        """Full harness run emits AGENT_START, TURN_START, TURN_END, AGENT_END."""
        realm = MockRealm([[_text_response()]])
        events: list[MvgeEvent] = []

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )
        mvge.on(MvgeEventType.AGENT_START, lambda e: events.append(e))
        mvge.on(MvgeEventType.AGENT_END, lambda e: events.append(e))
        mvge.on(MvgeEventType.TURN_START, lambda e: events.append(e))
        mvge.on(MvgeEventType.TURN_END, lambda e: events.append(e))

        result = await mvge.run("Hello")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP

        event_types = [e.type for e in events]
        assert MvgeEventType.AGENT_START in event_types
        assert MvgeEventType.TURN_START in event_types
        assert MvgeEventType.TURN_END in event_types
        assert MvgeEventType.AGENT_END in event_types

        start_idx = event_types.index(MvgeEventType.AGENT_START)
        end_idx = event_types.index(MvgeEventType.AGENT_END)
        assert start_idx < end_idx

        await mvge.close()

    @pytest.mark.asyncio
    async def test_inner_loop_runs_multiple_turns_for_spells(
        self, temp_session_dir: Path
    ) -> None:
        """Inner loop executes multiple turns when spells are cast."""
        realm = MockRealm(
            [
                [_spell_response()],
                [_text_response("Done after spell")],
            ]
        )
        events: list[MvgeEvent] = []

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )
        mvge.on(MvgeEventType.TURN_START, lambda e: events.append(e))
        mvge.on(MvgeEventType.TURN_END, lambda e: events.append(e))

        result = await mvge.run("Do something")

        assert isinstance(result, MvgeResponse)
        turn_starts = [e for e in events if e.type == MvgeEventType.TURN_START]
        turn_ends = [e for e in events if e.type == MvgeEventType.TURN_END]
        assert len(turn_starts) == 2
        assert len(turn_ends) == 2

        await mvge.close()

    @pytest.mark.asyncio
    async def test_outer_loop_resumes_on_follow_up(
        self, temp_session_dir: Path
    ) -> None:
        """Outer loop resumes when follow-up messages arrive after settling."""
        realm = MockRealm(
            [
                [_text_response("First response")],
                [_text_response("Second response")],
            ]
        )

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )

        turn_count = 0

        def on_turn_end(event: MvgeEvent) -> None:
            nonlocal turn_count
            turn_count += 1
            if turn_count == 1:
                mvge.follow_up("Follow-up question")

        mvge.on(MvgeEventType.TURN_END, on_turn_end)

        result = await mvge.run("Initial prompt")

        assert isinstance(result, MvgeResponse)
        assert turn_count == 2

        await mvge.close()

    @pytest.mark.asyncio
    async def test_steering_queue_drained_mid_run(self, temp_session_dir: Path) -> None:
        """Steering messages are drained between turns."""
        realm = MockRealm(
            [
                [_text_response("First")],
                [_text_response("Second")],
            ]
        )

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )

        turn_count = 0

        def on_turn_start(event: MvgeEvent) -> None:
            nonlocal turn_count
            turn_count += 1
            if turn_count == 1:
                mvge.steer("Steering input")

        mvge.on(MvgeEventType.TURN_START, on_turn_start)

        result = await mvge.run("Hello")

        assert isinstance(result, MvgeResponse)
        assert turn_count == 2

        await mvge.close()

    @pytest.mark.asyncio
    async def test_compaction_triggers_when_mana_pool_crowded(
        self, temp_session_dir: Path
    ) -> None:
        """Compaction triggers when context mana exceeds pool minus reserve."""
        large_text = "x" * 200000
        realm = MockRealm(
            [
                [_text_response(large_text, mana_used=90000)],
                [_text_response("Response after compaction")],
            ]
        )

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
            compaction=CompactionSettings(
                enabled=True, reserve_mana=16384, keep_recent_mana=20000
            ),
        )

        compaction_events: list[MvgeEvent] = []
        mvge.on(MvgeEventType.COMPACTION_START, lambda e: compaction_events.append(e))
        mvge.on(MvgeEventType.COMPACTION_END, lambda e: compaction_events.append(e))

        result = await mvge.run("Hello with lots of context")

        assert isinstance(result, MvgeResponse)
        compactions_started = [
            e for e in compaction_events if e.type == MvgeEventType.COMPACTION_START
        ]
        compactions_ended = [
            e for e in compaction_events if e.type == MvgeEventType.COMPACTION_END
        ]
        assert len(compactions_started) >= 1
        assert len(compactions_ended) >= 1

        await mvge.close()

    @pytest.mark.asyncio
    async def test_should_stop_after_turn_halts_loop(
        self, temp_session_dir: Path
    ) -> None:
        """should_stop_after_turn callback halts the loop after a turn."""
        realm = MockRealm(
            [
                [_text_response("First")],
                [_text_response("Should not reach")],
            ]
        )

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )

        turn_count = 0

        def on_turn_end(event: MvgeEvent) -> None:
            nonlocal turn_count
            turn_count += 1

        mvge.on(MvgeEventType.TURN_END, on_turn_end)

        await mvge.initialize()

        # Patch the loop's should_stop to halt after first turn
        original_build_callbacks = mvge._loop._build_callbacks

        def build_callbacks_with_stop() -> LoopCallbacks:
            callbacks = original_build_callbacks()

            async def should_stop() -> bool:
                return turn_count >= 1

            callbacks.should_stop_after_turn = should_stop
            return callbacks

        mvge._loop._build_callbacks = build_callbacks_with_stop

        result = await mvge.run("Hello")

        assert isinstance(result, MvgeResponse)
        assert turn_count == 1

        await mvge.close()

    @pytest.mark.asyncio
    async def test_prepare_next_turn_fires_between_turns(
        self, temp_session_dir: Path
    ) -> None:
        """prepare_next_turn callback fires between turns."""
        realm = MockRealm(
            [
                [_spell_response()],
                [_text_response("Done after spell")],
            ]
        )

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )

        prepare_count = 0

        await mvge.initialize()

        # Patch the loop's prepare_next_turn to count calls
        original_build_callbacks = mvge._loop._build_callbacks

        def build_callbacks_with_prepare() -> LoopCallbacks:
            callbacks = original_build_callbacks()

            async def prepare_next_turn(context: Any) -> Any:
                nonlocal prepare_count
                prepare_count += 1
                return context

            callbacks.prepare_next_turn = prepare_next_turn
            return callbacks

        mvge._loop._build_callbacks = build_callbacks_with_prepare

        result = await mvge.run("Do something")

        assert isinstance(result, MvgeResponse)
        assert prepare_count == 1

        await mvge.close()

    @pytest.mark.asyncio
    async def test_event_bus_receives_all_events(self, temp_session_dir: Path) -> None:
        """EventBus receives all lifecycle events during a run."""
        realm = MockRealm([[_text_response()]])

        mvge = _MockMvge(
            mock_realm=realm,
            session_dir=temp_session_dir,
        )

        received: list[MvgeEventType] = []
        bus = mvge._event_bus
        assert bus is not None

        for event_type in MvgeEventType:
            bus.on(event_type, lambda e, et=event_type: received.append(et))

        await mvge.run("Hello")

        assert MvgeEventType.AGENT_START in received
        assert MvgeEventType.AGENT_END in received

        await mvge.close()

    @pytest.mark.asyncio
    async def test_realm_stream_called_with_correct_invocations(
        self, temp_session_dir: Path
    ) -> None:
        """MockRealm receives invocations from the loop."""
        realm = MockRealm([[_text_response()]])
        mvge = _MockMvge(mock_realm=realm, session_dir=temp_session_dir)

        await mvge.run("Hello")

        assert realm.stream_calls == 1

        await mvge.close()

    @pytest.mark.asyncio
    async def test_harness_returns_final_response(self, temp_session_dir: Path) -> None:
        """Harness returns the final MvgeResponse from the loop."""
        realm = MockRealm(
            [
                [_spell_response()],
                [_text_response("Final answer")],
            ]
        )
        mvge = _MockMvge(mock_realm=realm, session_dir=temp_session_dir)

        result = await mvge.run("Do something")

        assert isinstance(result, MvgeResponse)
        assert result.stop_reason == StopReason.STOP
        text_blocks = [b for b in result.content if b.get("type") == "text"]
        assert any("Final answer" in b.get("text", "") for b in text_blocks)

        await mvge.close()
