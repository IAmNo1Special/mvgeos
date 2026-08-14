from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntryType

from mvgeos_agent.agent_session import MvgeTome


def _tome(tmp: str) -> tuple[MvgeTome, TomeLedger]:
    ledger = TomeLedger(Path(tmp))
    meta = ledger.create_tome("/tmp")
    tome = MvgeTome(ledger, meta)
    tome._started = True
    return tome, ledger


@pytest.mark.asyncio
async def test_record_message_async_defaults_parent_to_active_leaf() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome, ledger = _tome(tmp)

        e1 = await tome.record_message_async(role="user", content="msg 1")
        assert e1 is not None
        assert e1.parent_id is None
        assert await tome.active_leaf_id_async() == e1.id

        e2 = await tome.record_message_async(role="assistant", content="msg 2")
        assert e2 is not None
        assert e2.parent_id == e1.id
        assert await tome.active_leaf_id_async() == e2.id


@pytest.mark.asyncio
async def test_record_compaction_and_custom_async_persist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome, ledger = _tome(tmp)

        comp = await tome.record_compaction_async(
            summary="s", mana_before=10, retained_tail=[]
        )
        assert comp is not None
        custom = await tome.record_custom_async("note", {"k": "v"})
        assert custom is not None

        entries = await ledger.get_entries_async(tome.tome_id)
        types = {e.type for e in entries}
        assert TomeEntryType.COMPACTION in types
        assert TomeEntryType.CUSTOM in types


@pytest.mark.asyncio
async def test_record_compaction_async_keeps_first_kept_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome, ledger = _tome(tmp)
        comp = await tome.record_compaction_async(
            summary="s",
            mana_before=0,
            retained_tail=[],
            first_kept_entry_id="keep-1",
        )
        assert comp is not None
        entry = await ledger.get_entry_async(tome.tome_id, comp.id)
        assert entry is not None
        assert entry.payload["firstKeptEntryId"] == "keep-1"


@pytest.mark.asyncio
async def test_advance_leaf_async_swallows_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome, ledger = _tome(tmp)
        entry = await tome.record_message_async(role="user", content="x")
        assert entry is not None
        # Force the leaf-advance to fail; recording must not raise.
        original = ledger.append_leaf_async
        ledger.append_leaf_async = __import__(
            "unittest.mock", fromlist=["AsyncMock"]
        ).AsyncMock(side_effect=RuntimeError("boom"))
        try:
            await tome._advance_leaf_async(entry)
        finally:
            ledger.append_leaf_async = original


@pytest.mark.asyncio
async def test_recording_async_dropped_when_not_started() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome, _ledger = _tome(tmp)
        tome._started = False

        assert await tome.record_message_async(role="user", content="x") is None
        assert (
            await tome.record_compaction_async(
                summary="s", mana_before=0, retained_tail=[]
            )
            is None
        )
        assert await tome.record_custom_async("note") is None


@pytest.mark.asyncio
async def test_concurrent_async_recording_no_loss() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome, ledger = _tome(tmp)

        async def record(i: int) -> None:
            await tome.record_message_async(role="user", content=f"msg {i}")

        await asyncio.gather(*(record(i) for i in range(30)))

        entries = await ledger.get_entries_async(tome.tome_id)
        # Concurrent recording must not lose entries or corrupt the JSONL file.
        assert len([e for e in entries if e.payload.get("role") == "user"]) == 30
