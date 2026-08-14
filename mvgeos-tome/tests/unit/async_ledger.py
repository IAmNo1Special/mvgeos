from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntry, TomeEntryType


def _make_ledger(tmp_path: Path) -> tuple[TomeLedger, str]:
    ledger = TomeLedger(tmp_path)
    meta = ledger.create_tome(str(tmp_path))
    return ledger, meta.id


def _entry(content: str) -> TomeEntry:
    return TomeEntry(
        id=content,
        parent_id=None,
        type=TomeEntryType.MESSAGE,
        timestamp=0.0,
        payload={"role": "user", "content": content},
    )


@pytest.mark.asyncio
async def test_append_and_read_async_mirror_sync(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    await ledger.append_async(tid, _entry("a"))
    await ledger.append_async(tid, _entry("b"))

    entries = await ledger.get_entries_async(tid)
    assert [e.payload["content"] for e in entries] == ["a", "b"]

    entry = await ledger.get_entry_async(tid, "a")
    assert entry is not None
    assert entry.payload["content"] == "a"


@pytest.mark.asyncio
async def test_leaf_and_message_async(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    entry = await ledger.append_message_async(tid, "user", "hello")
    await ledger.append_leaf_async(tid, entry.id)

    assert await ledger.get_leaf_id_async(tid) == entry.id


@pytest.mark.asyncio
async def test_branched_tome_async_preserves_ancestors(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    e1 = await ledger.append_message_async(tid, "user", "one")
    await ledger.append_leaf_async(tid, e1.id)
    e2 = await ledger.append_message_async(tid, "user", "two")
    await ledger.append_leaf_async(tid, e2.id)

    forked = await ledger.create_branched_tome_async(tid, str(tmp_path), e1.id)
    ctx = await ledger.get_entries_for_context_async(forked.id, leaf_id=e1.id)
    assert [e.id for e in ctx] == [e1.id]


@pytest.mark.asyncio
async def test_open_tome_async(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    reopened = await ledger.open_tome_async(tid)
    assert reopened is not None
    assert reopened.id == tid


@pytest.mark.asyncio
async def test_create_tome_async(tmp_path: Path) -> None:
    ledger = TomeLedger(tmp_path)
    meta = await ledger.create_tome_async(str(tmp_path), tome_id="abc123")
    assert meta.id == "abc123"
    assert await ledger.open_tome_async("abc123") is not None


@pytest.mark.asyncio
async def test_custom_label_and_tome_info_async(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    custom = await ledger.append_custom_async(tid, {"type": "note", "data": {}})
    assert custom is not None
    label = await ledger.append_label_async(tid, "important")
    assert label is not None
    info = await ledger.append_tome_info_async(tid, {"name": "session"})
    assert info is not None

    entries = await ledger.get_entries_async(tid)
    types = {e.type for e in entries}
    assert TomeEntryType.CUSTOM in types
    assert TomeEntryType.LABEL in types
    assert TomeEntryType.TOME_INFO in types


@pytest.mark.asyncio
async def test_compaction_and_context_async(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    e1 = await ledger.append_message_async(tid, "user", "one")
    await ledger.append_leaf_async(tid, e1.id)
    comp = await ledger.append_compaction_async(tid, {"summary": "s"})
    assert comp is not None

    ctx = await ledger.get_entries_for_context_async(tid, leaf_id=e1.id)
    assert [e.id for e in ctx] == [e1.id]


@pytest.mark.asyncio
async def test_open_recent_async(tmp_path: Path) -> None:
    ledger = TomeLedger(tmp_path)
    await ledger.create_tome_async(str(tmp_path), tome_id="recent1")
    meta = await ledger.open_recent_async(str(tmp_path))
    assert meta is not None
    assert meta.id == "recent1"


@pytest.mark.asyncio
async def test_concurrent_appends_no_race_or_loss(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    ids = [f"msg-{i}" for i in range(50)]

    await asyncio.gather(*(ledger.append_async(tid, _entry(i)) for i in ids))

    entries = await ledger.get_entries_async(tid)
    recorded = {e.id for e in entries}
    assert recorded == set(ids)


@pytest.mark.asyncio
async def test_concurrent_reads_and_writes_stay_consistent(tmp_path: Path) -> None:
    ledger, tid = _make_ledger(tmp_path)
    ids = [f"msg-{i}" for i in range(40)]

    async def writer(i: str) -> None:
        await ledger.append_async(tid, _entry(i))

    async def reader() -> list[TomeEntry]:
        return await ledger.get_entries_async(tid)

    results = await asyncio.gather(
        *(writer(i) for i in ids),
        *(reader() for _ in range(10)),
    )
    readers = results[40:]
    for snapshot in readers:
        assert all(e.type == TomeEntryType.MESSAGE for e in snapshot)
