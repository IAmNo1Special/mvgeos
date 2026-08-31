from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook
from mvgeos_tome.types import TomeMetadata

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.types import TomeResumeError


def _metadata(tome_id: str = "a" * 32, cwd: str = "/test") -> TomeMetadata:
    return TomeMetadata(id=tome_id, created_at="now", cwd=cwd)


def _mock_runner() -> MagicMock:
    runner = MagicMock(spec=RuneRunner)
    runner.emit_async = AsyncMock()
    runner.emit_first = AsyncMock(return_value=None)
    return runner


def _started_source(ledger: MagicMock, runner: MagicMock) -> MvgeTome:
    source = MvgeTome(ledger, _metadata(cwd="/test"), runner)
    return source


async def _emitted(runner: MagicMock, hook: SigilHook) -> list[dict]:
    return [c.args[1] for c in runner.emit_async.await_args_list if c.args[0] == hook]


def _track(runner: MagicMock) -> list[SigilHook]:
    order: list[SigilHook] = []

    async def _record(hook: SigilHook, data: dict) -> None:
        order.append(hook)

    runner.emit_first = AsyncMock(side_effect=_record)
    runner.emit_async = AsyncMock(side_effect=_record)
    return order


async def _assert_source_still_running(runner: MagicMock, source: MvgeTome) -> None:
    shutdowns = await _emitted(runner, SigilHook.SESSION_SHUTDOWN)
    assert shutdowns == []
    assert source.record_message("user", "hi") is not None


class TestFactories:
    @pytest.mark.asyncio
    async def test_create_creates_new_tome(self) -> None:
        ledger = MagicMock()
        ledger.create_tome.return_value = _metadata()
        runner = _mock_runner()

        tome = await MvgeTome.create(ledger, cwd="/proj", runner=runner)

        ledger.create_tome.assert_called_once_with("/proj")
        ledger.open_tome.assert_not_called()
        assert isinstance(tome, MvgeTome)
        assert tome.tome_id == _metadata().id
        starts = await _emitted(runner, SigilHook.SESSION_START)
        assert starts == [
            {
                "reason": "startup",
                "tomeId": _metadata().id,
                "tomeFile": tome.tome_file,
            }
        ]

    @pytest.mark.asyncio
    async def test_create_default_cwd_is_process_cwd(self) -> None:
        ledger = MagicMock()
        ledger.create_tome.return_value = _metadata()

        await MvgeTome.create(ledger)

        ledger.create_tome.assert_called_once_with(str(Path.cwd()))

    @pytest.mark.asyncio
    async def test_open_resumes_existing_tome(self) -> None:
        resumed = _metadata("b" * 32)
        ledger = MagicMock()
        ledger.open_tome.return_value = resumed
        runner = _mock_runner()

        tome = await MvgeTome.open(ledger, "b" * 32, runner=runner)

        ledger.open_tome.assert_called_once_with("b" * 32)
        ledger.create_tome.assert_not_called()
        assert tome.metadata is resumed
        starts = await _emitted(runner, SigilHook.SESSION_START)
        assert len(starts) == 1
        assert starts[0]["reason"] == "resume"
        assert starts[0]["tomeId"] == resumed.id

    @pytest.mark.asyncio
    async def test_open_missing_target_raises(self) -> None:
        ledger = MagicMock()
        ledger.open_tome.return_value = None

        with pytest.raises(TomeResumeError, match="missing-tome"):
            await MvgeTome.open(ledger, "missing-tome")
        ledger.create_tome.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_or_create_without_resume(self) -> None:
        ledger = MagicMock()
        ledger.create_tome.return_value = _metadata()
        runner = _mock_runner()

        tome = await MvgeTome.open_or_create(ledger, cwd="/proj", runner=runner)

        ledger.create_tome.assert_called_once_with("/proj")
        assert tome.tome_id == _metadata().id

    @pytest.mark.asyncio
    async def test_open_or_create_with_resume(self) -> None:
        resumed = _metadata("b" * 32)
        ledger = MagicMock()
        ledger.open_tome.return_value = resumed
        runner = _mock_runner()

        tome = await MvgeTome.open_or_create(
            ledger, tome_resume="b" * 32, runner=runner
        )

        ledger.open_tome.assert_called_once_with("b" * 32)
        assert tome.metadata is resumed


class TestFork:
    @pytest.mark.asyncio
    async def test_success_starts_branched_tome(self) -> None:
        ledger = MagicMock()
        source_meta = _metadata(cwd="/test")
        branched = _metadata("c" * 32, cwd="/test")
        ledger.create_branched_tome.return_value = branched
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.fork("entry-1")

        ledger.create_branched_tome.assert_called_once_with(
            parent_tome_id=source_meta.id,
            cwd="/test",
            fork_from_leaf_id="entry-1",
        )
        assert result is not None
        assert result.tome_id == branched.id
        forks = await _emitted(runner, SigilHook.SESSION_SHUTDOWN)
        assert forks[-1]["reason"] == "fork"
        starts = await _emitted(runner, SigilHook.SESSION_START)
        assert starts[-1]["reason"] == "fork"
        assert starts[-1]["tomeId"] == branched.id

    @pytest.mark.asyncio
    async def test_success_hook_order(self) -> None:
        ledger = MagicMock()
        branched = _metadata("c" * 32, cwd="/test")
        ledger.create_branched_tome.return_value = branched
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")
        order = _track(runner)

        result = await source.fork("entry-1")

        assert result is not None
        assert order == [
            SigilHook.SESSION_BEFORE_FORK,
            SigilHook.SESSION_SHUTDOWN,
            SigilHook.SESSION_START,
        ]

    @pytest.mark.asyncio
    async def test_cancelled_by_sigil_returns_none(self) -> None:
        ledger = MagicMock()
        runner = _mock_runner()
        runner.emit_first.return_value = {"cancel": True}
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.fork("entry-1")

        assert result is None
        ledger.create_branched_tome.assert_not_called()

    @pytest.mark.asyncio
    async def test_ledger_error_returns_none(self) -> None:
        ledger = MagicMock()
        ledger.create_branched_tome.side_effect = ValueError("boom")
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.fork("entry-1")

        assert result is None
        await _assert_source_still_running(runner, source)


class TestSwitch:
    @pytest.mark.asyncio
    async def test_success_resumes_target_tome(self) -> None:
        target_meta = _metadata("d" * 32)
        ledger = MagicMock()
        ledger.open_tome.return_value = target_meta
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")
        target_file = Path("/tomes") / f"{'d' * 32}.jsonl"

        result = await source.switch(target_file)

        ledger.open_tome.assert_called_once_with("d" * 32)
        assert result is not None
        assert result.tome_id == target_meta.id
        shutdowns = await _emitted(runner, SigilHook.SESSION_SHUTDOWN)
        assert shutdowns[-1]["reason"] == "resume"
        assert shutdowns[-1]["targetSessionFile"] == str(target_file)
        starts = await _emitted(runner, SigilHook.SESSION_START)
        assert starts[-1]["reason"] == "resume"

    @pytest.mark.asyncio
    async def test_success_hook_order(self) -> None:
        target_meta = _metadata("d" * 32)
        ledger = MagicMock()
        ledger.open_tome.return_value = target_meta
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")
        order = _track(runner)
        target_file = Path("/tomes") / f"{'d' * 32}.jsonl"

        result = await source.switch(target_file)

        assert result is not None
        assert order == [
            SigilHook.SESSION_BEFORE_SWITCH,
            SigilHook.SESSION_SHUTDOWN,
            SigilHook.SESSION_START,
        ]

    @pytest.mark.asyncio
    async def test_cancelled_by_sigil_returns_none(self) -> None:
        ledger = MagicMock()
        runner = _mock_runner()
        runner.emit_first.return_value = {"cancel": True}
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.switch(Path("/t/x.jsonl"))

        assert result is None
        ledger.open_tome.assert_not_called()

    @pytest.mark.asyncio
    async def test_unparseable_target_file_returns_none(self) -> None:
        ledger = MagicMock()
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.switch(Path("/t/not-a-tome.jsonl"))

        assert result is None
        ledger.open_tome.assert_not_called()
        await _assert_source_still_running(runner, source)

    @pytest.mark.asyncio
    async def test_unknown_target_tome_returns_none(self) -> None:
        ledger = MagicMock()
        ledger.open_tome.return_value = None
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.switch(Path("/t") / f"{'e' * 32}.jsonl")

        assert result is None
        await _assert_source_still_running(runner, source)

    @pytest.mark.asyncio
    async def test_open_tome_error_returns_none(self) -> None:
        ledger = MagicMock()
        ledger.open_tome.side_effect = ValueError("boom")
        runner = _mock_runner()
        source = _started_source(ledger, runner)
        await source.start(reason="startup")

        result = await source.switch(Path("/t") / f"{'e' * 32}.jsonl")

        assert result is None
        await _assert_source_still_running(runner, source)
