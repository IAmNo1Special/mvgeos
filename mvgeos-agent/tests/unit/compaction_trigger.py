from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_provider.types import Model, RealmResponse

from mvgeos_agent.harness.compaction import CompactionRunner, CompactionSettings
from mvgeos_agent.types import (
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    StopReason,
    SummonerRequest,
)


def _model() -> Model:
    return Model(
        id="test-model",
        name="Test",
        realm="test",
        base_url="",
        api_key="",
        context_window=1000,
    )


def _long_transcript() -> list[MvgeInvocation]:
    invocations: list[MvgeInvocation] = []
    for index in range(8):
        invocations.append(SummonerRequest(role="user", content=f"ask {index} " * 80))
        invocations.append(
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": f"reply {index} " * 80}],
                stop_reason=StopReason.STOP,
                mana_usage={"total": 900},
            )
        )
    return invocations


class Recorder:
    def __init__(self) -> None:
        self.events: list[MvgeEvent] = []

    async def __call__(self, event: MvgeEvent) -> None:
        self.events.append(event)

    def types(self) -> list[MvgeEventType]:
        return [event.type for event in self.events]


def _realm(summary: str = "## Goal\nShip it.") -> Any:
    realm = MagicMock()
    realm.complete = AsyncMock(
        return_value=RealmResponse(
            model=_model(),
            invocation=MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": summary}],
                stop_reason=StopReason.STOP,
            ),
        )
    )
    return realm


class TestNoCompactionNeeded:
    @pytest.mark.asyncio
    async def test_short_transcript_returns_none(self) -> None:
        runner = CompactionRunner(realm=_realm(), model=_model(), emit=Recorder())

        result = await runner.maybe_compact(
            [SummonerRequest(role="user", content="hi")]
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_disabled_settings_never_compact(self) -> None:
        emit = Recorder()
        runner = CompactionRunner(
            realm=_realm(),
            model=_model(),
            emit=emit,
            settings=CompactionSettings(enabled=False),
        )

        result = await runner.maybe_compact(_long_transcript())

        assert result is None
        assert MvgeEventType.COMPACTION_START not in emit.types()

    @pytest.mark.asyncio
    async def test_realm_not_called_when_below_threshold(self) -> None:
        realm = _realm()
        runner = CompactionRunner(realm=realm, model=_model(), emit=Recorder())

        await runner.maybe_compact([SummonerRequest(role="user", content="hi")])

        realm.complete.assert_not_called()


class TestCompactionRuns:
    @pytest.mark.asyncio
    async def test_returns_shorter_transcript(self) -> None:
        runner = CompactionRunner(
            realm=_realm(),
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )
        invocations = _long_transcript()

        result = await runner.maybe_compact(invocations)

        assert result is not None
        assert len(result) < len(invocations)

    @pytest.mark.asyncio
    async def test_summary_is_first_invocation(self) -> None:
        runner = CompactionRunner(
            realm=_realm("## Goal\nShip it."),
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )

        result = await runner.maybe_compact(_long_transcript())

        assert result is not None
        first = result[0]
        assert isinstance(first, SummonerRequest)
        assert "Ship it." in str(first.content)

    @pytest.mark.asyncio
    async def test_emits_start_and_end_events(self) -> None:
        emit = Recorder()
        runner = CompactionRunner(
            realm=_realm(),
            model=_model(),
            emit=emit,
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )

        await runner.maybe_compact(_long_transcript())

        types = emit.types()
        assert MvgeEventType.COMPACTION_START in types
        assert MvgeEventType.COMPACTION_END in types

    @pytest.mark.asyncio
    async def test_realm_called_without_spells(self) -> None:
        realm = _realm()
        runner = CompactionRunner(
            realm=realm,
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )

        await runner.maybe_compact(_long_transcript())

        config = realm.complete.await_args.args[2]
        assert not config.tools


class TestCompactionFailure:
    @pytest.mark.asyncio
    async def test_realm_error_leaves_transcript_untouched(self) -> None:
        realm = MagicMock()
        realm.complete = AsyncMock(
            return_value=RealmResponse(
                model=_model(),
                error_message="rate limited",
                error_code="rate_limited",
            )
        )
        runner = CompactionRunner(
            realm=realm,
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )

        result = await runner.maybe_compact(_long_transcript())

        assert result is None

    @pytest.mark.asyncio
    async def test_realm_exception_does_not_propagate(self) -> None:
        realm = MagicMock()
        realm.complete = AsyncMock(side_effect=RuntimeError("boom"))
        runner = CompactionRunner(
            realm=realm,
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )

        result = await runner.maybe_compact(_long_transcript())

        assert result is None

    @pytest.mark.asyncio
    async def test_failure_reported_on_end_event(self) -> None:
        realm = MagicMock()
        realm.complete = AsyncMock(side_effect=RuntimeError("boom"))
        emit = Recorder()
        runner = CompactionRunner(
            realm=realm,
            model=_model(),
            emit=emit,
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )

        await runner.maybe_compact(_long_transcript())

        end = [e for e in emit.events if e.type == MvgeEventType.COMPACTION_END]
        assert end
        assert end[-1].data.get("error")


class TestTomePersistence:
    @pytest.mark.asyncio
    async def test_appends_compaction_entry(self) -> None:
        tome = MagicMock()
        tome.record_compaction = MagicMock()
        runner = CompactionRunner(
            realm=_realm(),
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
            tome=tome,
        )

        await runner.maybe_compact(_long_transcript())

        tome.record_compaction.assert_called_once()
        payload = tome.record_compaction.call_args.kwargs
        assert "summary" in payload
        assert "mana_before" in payload
        assert "retained_tail" in payload

    @pytest.mark.asyncio
    async def test_compaction_reaches_the_loop(self) -> None:
        """The runner must actually swap the transcript during a real run."""
        from collections.abc import AsyncIterator

        from mvgeos_agent.loop import MvgeLoop
        from mvgeos_agent.types import MvgeSpell, MvgeState

        spell = MagicMock(spec=MvgeSpell)
        spell.name = "x"
        spell.description = "spell"
        spell.parameters = {"type": "object", "properties": {}}
        spell.execute = AsyncMock(return_value={"ok": True})

        state = MvgeState(
            system_prompt="test",
            model={"id": "test-model"},
            spells=[spell],
            invocations=_long_transcript(),
        )
        loop = MvgeLoop(state)
        runner = CompactionRunner(
            realm=_realm(),
            model=_model(),
            emit=loop.emit,
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
        )
        loop.set_after_invocation(runner.maybe_compact)

        seen: list[list[MvgeInvocation]] = []
        replies = [
            RealmResponse(
                model=_model(),
                invocation=MvgeResponse(
                    role="assistant",
                    content=[
                        {
                            "type": "tool_call",
                            "tool_call": {"id": "1", "name": "x", "arguments": {}},
                        }
                    ],
                    stop_reason=StopReason.SPELL_USE,
                ),
            ),
            RealmResponse(
                model=_model(),
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "done"}],
                    stop_reason=StopReason.STOP,
                ),
            ),
        ]
        turn = -1

        def stream_fn(
            invocations: list[MvgeInvocation], signal: Any | None = None
        ) -> AsyncIterator[Any]:
            nonlocal turn
            turn += 1
            seen.append(list(invocations))
            response = replies[min(turn, len(replies) - 1)]

            async def gen() -> AsyncIterator[Any]:
                yield response

            return gen()

        await loop.run(stream_fn, {"id": "test-model"}, "none")

        # Turn two must be shorter: compaction replaced the history.
        assert len(seen) == 2
        assert len(seen[1]) < len(seen[0])
        assert "Summary of earlier conversation" in str(seen[1][0].content)

    @pytest.mark.asyncio
    async def test_no_tome_is_tolerated(self) -> None:
        runner = CompactionRunner(
            realm=_realm(),
            model=_model(),
            emit=Recorder(),
            settings=CompactionSettings(reserve_mana=200, keep_recent_mana=200),
            tome=None,
        )

        result = await runner.maybe_compact(_long_transcript())

        assert result is not None
