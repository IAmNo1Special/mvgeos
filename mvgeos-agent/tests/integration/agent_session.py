from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeMetadata

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.types import TomeResumeError


@pytest.fixture
def tome_ledger() -> TomeLedger:
    with tempfile.TemporaryDirectory() as tmp:
        yield TomeLedger(Path(tmp))


@pytest.fixture
def tome_metadata(tome_ledger: TomeLedger) -> TomeMetadata:
    return tome_ledger.create_tome("/test")


@pytest.fixture
def runner() -> RuneRunner:
    return RuneRunner()


@pytest.mark.asyncio
async def test_start_emits_session_start(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    handler = MagicMock()
    runner.register_handler(SigilHook.SESSION_START, handler)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")
    handler.assert_called_once()
    call_data = handler.call_args[0][0]
    assert call_data["reason"] == "startup"
    assert call_data["tomeId"] == tome_metadata.id


@pytest.mark.asyncio
async def test_start_idempotent(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    handler = MagicMock()
    runner.register_handler(SigilHook.SESSION_START, handler)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")
    await tome.start(reason="startup")
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_emits_session_shutdown(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    handler = MagicMock()
    runner.register_handler(SigilHook.SESSION_SHUTDOWN, handler)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")
    await tome.shutdown(reason="quit")
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_with_target_file(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    handler = MagicMock()
    runner.register_handler(SigilHook.SESSION_SHUTDOWN, handler)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")
    await tome.shutdown(reason="resume", target_session_file="/path/to/new")
    call_data = handler.call_args[0][0]
    assert call_data["reason"] == "resume"
    assert call_data["targetSessionFile"] == "/path/to/new"


@pytest.mark.asyncio
async def test_shutdown_noop_if_not_started(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    handler = MagicMock()
    runner.register_handler(SigilHook.SESSION_SHUTDOWN, handler)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.shutdown(reason="quit")
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_before_switch_cancellable(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()

    def canceller(data: dict) -> dict:
        return {"cancel": True}

    runner.register_handler(SigilHook.SESSION_BEFORE_SWITCH, canceller)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    result = await tome.before_switch("/path/to/target")
    assert result is not None
    assert result["cancelled"]


@pytest.mark.asyncio
async def test_before_switch_not_cancelled(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    result = await tome.before_switch("/path/to/target")
    assert result is not None
    assert not result["cancelled"]


@pytest.mark.asyncio
async def test_before_fork_cancellable(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()

    def canceller(data: dict) -> dict:
        return {"cancel": True}

    runner.register_handler(SigilHook.SESSION_BEFORE_FORK, canceller)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    result = await tome.before_fork("entry-123")
    assert result is not None
    assert result["cancelled"]


@pytest.mark.asyncio
async def test_properties(tome_ledger: TomeLedger, tome_metadata: TomeMetadata) -> None:
    tome = MvgeTome(tome_ledger, tome_metadata)
    assert tome.tome_id == tome_metadata.id
    assert tome.metadata is tome_metadata


@pytest.mark.asyncio
async def test_bind_runner(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    tome = MvgeTome(tome_ledger, tome_metadata)
    runner = RuneRunner()
    tome.bind_runner(runner)
    assert tome._rune_runner is runner


@pytest.mark.asyncio
async def test_record_message_not_started(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    tome = MvgeTome(tome_ledger, tome_metadata)
    result = tome.record_message("user", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_record_custom_not_started(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    tome = MvgeTome(tome_ledger, tome_metadata)
    result = tome.record_custom("test_type", {"key": "value"})
    assert result is None


@pytest.mark.asyncio
async def test_record_message_started(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    result = tome.record_message("user", "hello", model="test-model")
    assert result is not None
    assert result.type.value == "message"
    assert result.payload.get("role") == "user"
    assert result.payload.get("content") == "hello"


@pytest.mark.asyncio
async def test_record_custom_started(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    result = tome.record_custom("test_type", {"key": "value"})
    assert result is not None
    assert result.type.value == "custom"
    assert result.payload.get("type") == "test_type"


@pytest.mark.asyncio
async def test_safe_emit_no_runner(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    # Should not raise when runner is None
    tome = MvgeTome(tome_ledger, tome_metadata)
    await tome._safe_emit(SigilHook.SESSION_START, {"test": "data"})


@pytest.mark.asyncio
async def test_safe_emit_first_no_runner(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    # Should return None when runner is None
    tome = MvgeTome(tome_ledger, tome_metadata)
    result = await tome._safe_emit_first(SigilHook.SESSION_START, {"test": "data"})
    assert result is None


def _record_shutdowns(rune_runner: RuneRunner) -> list[SigilHook]:
    seen: list[SigilHook] = []

    def recorder(data: dict) -> dict:
        seen.append(SigilHook.SESSION_SHUTDOWN)
        return {}

    rune_runner.register_handler(SigilHook.SESSION_SHUTDOWN, recorder)
    return seen


def _assert_no_shutdown(seen: list[SigilHook]) -> None:
    assert SigilHook.SESSION_SHUTDOWN not in seen


@pytest.mark.asyncio
async def test_factory_create_starts_session(
    tome_ledger: TomeLedger, runner: RuneRunner
) -> None:
    starts: list[dict] = []
    runner.register_handler(SigilHook.SESSION_START, lambda d: starts.append(d))

    tome = await MvgeTome.create(tome_ledger, cwd="/custom/dir", runner=runner)

    assert isinstance(tome, MvgeTome)
    assert tome.metadata.cwd == "/custom/dir"
    assert len(starts) == 1
    assert starts[0]["reason"] == "startup"


@pytest.mark.asyncio
async def test_factory_open_resumes_session(
    tome_ledger: TomeLedger, runner: RuneRunner, tome_metadata: TomeMetadata
) -> None:
    starts: list[dict] = []
    runner.register_handler(SigilHook.SESSION_START, lambda d: starts.append(d))

    tome = await MvgeTome.open(tome_ledger, tome_metadata.id, runner=runner)

    assert isinstance(tome, MvgeTome)
    assert tome.tome_id == tome_metadata.id
    assert len(starts) == 1
    assert starts[0]["reason"] == "resume"


@pytest.mark.asyncio
async def test_factory_open_missing_raises(
    tome_ledger: TomeLedger, runner: RuneRunner
) -> None:
    with pytest.raises(TomeResumeError):
        await MvgeTome.open(tome_ledger, "nonexistent", runner=runner)


@pytest.mark.asyncio
async def test_factory_open_or_create(
    tome_ledger: TomeLedger, runner: RuneRunner, tome_metadata: TomeMetadata
) -> None:
    tome1 = await MvgeTome.open_or_create(tome_ledger, cwd="/proj", runner=runner)
    assert tome1.metadata.cwd == "/proj"

    tome2 = await MvgeTome.open_or_create(
        tome_ledger, tome_resume=tome_metadata.id, runner=runner
    )
    assert tome2.tome_id == tome_metadata.id


@pytest.mark.asyncio
async def test_switch_cancelled(
    runner: RuneRunner, tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    def canceller(data: dict) -> dict:
        return {"cancel": True}

    runner.register_handler(SigilHook.SESSION_BEFORE_SWITCH, canceller)
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")
    seen = _record_shutdowns(runner)

    result = await source.switch(Path("/path/to/target.jsonl"))
    assert result is None
    _assert_no_shutdown(seen)


@pytest.mark.asyncio
async def test_switch_invalid_tome_id(
    runner: RuneRunner, tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")
    seen = _record_shutdowns(runner)

    result = await source.switch(Path("/path/to/invalid.jsonl"))
    assert result is None
    _assert_no_shutdown(seen)


@pytest.mark.asyncio
async def test_switch_tome_not_found(
    runner: RuneRunner, tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")
    seen = _record_shutdowns(runner)

    target_file = Path("/path/to") / f"{'a' * 32}.jsonl"
    result = await source.switch(target_file)
    assert result is None
    _assert_no_shutdown(seen)


@pytest.mark.asyncio
async def test_switch_success(
    tome_ledger: TomeLedger, runner: RuneRunner, tome_metadata: TomeMetadata
) -> None:
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")

    meta2 = tome_ledger.create_tome("/test2")
    target_file = tome_ledger.tome_file(meta2.id)

    result = await source.switch(target_file)
    assert result is not None
    assert result.tome_id == meta2.id


@pytest.mark.asyncio
async def test_fork_cancelled(
    tome_ledger: TomeLedger, runner: RuneRunner, tome_metadata: TomeMetadata
) -> None:
    def canceller(data: dict) -> dict:
        return {"cancel": True}

    runner.register_handler(SigilHook.SESSION_BEFORE_FORK, canceller)
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")
    seen = _record_shutdowns(runner)

    entry = tome_ledger.append_message(
        tome_id=source.tome_id, role="user", content="test"
    )

    result = await source.fork(entry.id)
    assert result is None
    _assert_no_shutdown(seen)


@pytest.mark.asyncio
async def test_fork_ledger_rejection_keeps_source_running(
    tome_ledger: TomeLedger, runner: RuneRunner
) -> None:
    ghost_meta = TomeMetadata(id="f" * 32, created_at="now", cwd="/test")
    source = MvgeTome(tome_ledger, ghost_meta, runner)
    await source.start(reason="startup")
    seen = _record_shutdowns(runner)

    result = await source.fork("entry-1")
    assert result is None
    _assert_no_shutdown(seen)


@pytest.mark.asyncio
async def test_fork_success(
    tome_ledger: TomeLedger, runner: RuneRunner, tome_metadata: TomeMetadata
) -> None:
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")

    entry = tome_ledger.append_message(
        tome_id=source.tome_id, role="user", content="test"
    )

    result = await source.fork(entry.id)
    assert result is not None
    assert result.tome_id != source.tome_id

    branched_entries = tome_ledger.get_entries(result.tome_id)
    assert any(e.id == entry.id for e in branched_entries)


@pytest.mark.asyncio
async def test_fork_invalid_entry_creates_branched(
    tome_ledger: TomeLedger, runner: RuneRunner, tome_metadata: TomeMetadata
) -> None:
    source = MvgeTome(tome_ledger, tome_metadata, runner)
    await source.start(reason="startup")

    result = await source.fork("nonexistent-entry")
    assert result is not None
    assert result.tome_id != source.tome_id


@pytest.mark.asyncio
async def test_mvge_tome_create_initializes_valid_tome() -> None:
    with tempfile.TemporaryDirectory() as direct_dir:
        ledger = TomeLedger(Path(direct_dir))
        tome = await MvgeTome.create(ledger)

        assert tome.metadata.cwd == str(Path.cwd())
        assert tome.metadata.parent_tome_id is None
        assert tome.record_custom("probe", {}) is not None
