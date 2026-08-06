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
async def test_switch_to_cancelled(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()

    def canceller(data: dict) -> dict:
        return {"cancel": True}

    runner.register_handler(SigilHook.SESSION_BEFORE_SWITCH, canceller)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    result = await tome.switch_to(Path("/path/to/target.jsonl"), Path("/tmp"))
    assert result is None


@pytest.mark.asyncio
async def test_switch_to_invalid_tome_id(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    # Invalid format - no 32-char hex
    result = await tome.switch_to(Path("/path/to/invalid.jsonl"), Path("/tmp"))
    assert result is None


@pytest.mark.asyncio
async def test_switch_to_tome_not_found(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    # Valid format but tome doesn't exist
    result = await tome.switch_to(Path("/path/to/" + "a" * 32 + ".jsonl"), Path("/tmp"))
    assert result is None


@pytest.mark.asyncio
async def test_switch_to_success(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    # Create a second tome to switch to
    meta2 = tome_ledger.create_tome("/test2")
    target_file = tome_ledger.tome_file(meta2.id)

    result = await tome.switch_to(target_file, Path("/tmp"))
    assert result is not None
    assert result.tome_id == meta2.id


@pytest.mark.asyncio
async def test_fork_at_cancelled(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()

    def canceller(data: dict) -> dict:
        return {"cancel": True}

    runner.register_handler(SigilHook.SESSION_BEFORE_FORK, canceller)
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    # Add an entry to fork from
    entry = tome_ledger.append_message(
        tome_id=tome_metadata.id, role="user", content="test"
    )

    result = await tome.fork_at(entry.id, Path("/tmp"))
    assert result is None


@pytest.mark.asyncio
async def test_fork_at_success(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    # Add an entry to fork from
    entry = tome_ledger.append_message(
        tome_id=tome_metadata.id, role="user", content="test"
    )

    result = await tome.fork_at(entry.id, Path("/tmp"))
    assert result is not None
    assert result.tome_id != tome_metadata.id


@pytest.mark.asyncio
async def test_fork_at_invalid_entry_creates_branched(
    tome_ledger: TomeLedger, tome_metadata: TomeMetadata
) -> None:
    runner = RuneRunner()
    tome = MvgeTome(tome_ledger, tome_metadata, runner)
    await tome.start(reason="startup")

    # Invalid entry ID - ledger doesn't validate, creates branched tome anyway
    result = await tome.fork_at("nonexistent-entry", Path("/tmp"))
    assert result is not None
    assert result.tome_id != tome_metadata.id


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
