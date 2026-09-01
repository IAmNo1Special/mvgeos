from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mvgeos_tome import TomeLedger
from mvgeos_tome.types import TomeEntryType


def _write_fixture_session(
    tome_dir: Path, filename: str, lines: list[dict[str, Any]]
) -> Path:
    target = tome_dir / filename
    with target.open("w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")
    return target


def test_v1_session_fixture_transparent_upgrade(tmp_path: Path) -> None:
    # v1 fixture: header has no version field, entries are flat without id or parentId
    header = {
        "type": "session",
        "id": "fixture-v1-session",
        "timestamp": "2026-07-01T12:00:00Z",
        "cwd": "/workspace/project-v1",
    }
    entry1 = {
        "type": "message",
        "timestamp": 1000.0,
        "payload": {"role": "user", "content": "hello v1"},
    }
    entry2 = {
        "type": "message",
        "timestamp": 1001.0,
        "payload": {"role": "assistant", "content": "hello response"},
    }
    entry3 = {
        "type": "compaction",
        "timestamp": 1002.0,
        "payload": {
            "summary": "Compacted history",
            "manaBefore": 1000,
            "firstKeptEntryIndex": 1,
        },
    }
    _write_fixture_session(
        tmp_path, "fixture-v1-session.jsonl", [header, entry1, entry2, entry3]
    )

    ledger = TomeLedger(tmp_path)
    meta = ledger.open_tome("fixture-v1-session")
    assert meta is not None
    assert meta.id == "fixture-v1-session"
    assert meta.cwd == "/workspace/project-v1"

    entries = ledger.get_entries("fixture-v1-session")
    assert len(entries) == 3

    # Check v1 -> v2 chain
    assert entries[0].id is not None
    assert entries[0].parent_id is None
    assert entries[0].type == TomeEntryType.MESSAGE
    assert entries[0].payload["content"] == "hello v1"

    assert entries[1].id is not None
    assert entries[1].parent_id == entries[0].id
    assert entries[1].type == TomeEntryType.MESSAGE

    assert entries[2].id is not None
    assert entries[2].parent_id == entries[1].id
    assert entries[2].type == TomeEntryType.COMPACTION
    # Check compaction index was migrated to id
    assert entries[2].payload["firstKeptEntryId"] == entries[1].id
    assert "firstKeptEntryIndex" not in entries[2].payload


def test_v2_session_fixture_transparent_upgrade(tmp_path: Path) -> None:
    # v2 fixture: version is 2, entries have id and parentId, but legacy role names
    header = {
        "type": "session",
        "version": 2,
        "id": "fixture-v2-session",
        "timestamp": "2026-07-01T12:00:00Z",
        "cwd": "/workspace/project-v2",
        "activeLeafId": "v2-e2",
    }
    entry1 = {
        "id": "v2-e1",
        "parentId": None,
        "type": "message",
        "timestamp": 1000.0,
        "payload": {"role": "user", "content": "run hook"},
    }
    entry2 = {
        "id": "v2-e2",
        "parentId": "v2-e1",
        "type": "hookMessage",
        "timestamp": 1001.0,
        "payload": {"role": "hookMessage", "content": "custom hook result"},
    }
    _write_fixture_session(
        tmp_path, "fixture-v2-session.jsonl", [header, entry1, entry2]
    )

    ledger = TomeLedger(tmp_path)
    entries = ledger.get_entries("fixture-v2-session")
    assert len(entries) == 2

    assert entries[0].id == "v2-e1"
    assert entries[0].type == TomeEntryType.MESSAGE

    assert entries[1].id == "v2-e2"
    assert entries[1].parent_id == "v2-e1"
    # hookMessage migrated to custom
    assert entries[1].type == TomeEntryType.CUSTOM


def test_round_trip_v1_to_v3_lossless_persistence(tmp_path: Path) -> None:
    header = {
        "type": "session",
        "id": "roundtrip-v1",
        "timestamp": "2026-07-01T12:00:00Z",
        "cwd": "/workspace/roundtrip",
    }
    entry1 = {
        "type": "message",
        "timestamp": 1000.0,
        "payload": {"role": "user", "content": "first message"},
    }
    _write_fixture_session(tmp_path, "roundtrip-v1.jsonl", [header, entry1])

    ledger = TomeLedger(tmp_path)
    entries = ledger.get_entries("roundtrip-v1")
    assert len(entries) == 1
    first_id = entries[0].id

    # Append a new message and leaf to the loaded tome
    new_entry = ledger.append_message(
        "roundtrip-v1", "assistant", "response text", parent_id=first_id
    )
    ledger.append_leaf("roundtrip-v1", new_entry.id)

    # Verify that file can be re-opened with a clean new TomeLedger instance
    ledger2 = TomeLedger(tmp_path)
    reloaded_entries = ledger2.get_entries("roundtrip-v1")
    assert len(reloaded_entries) == 3  # message 1, message 2, leaf
    assert reloaded_entries[0].id == first_id
    assert reloaded_entries[1].id == new_entry.id
    assert reloaded_entries[1].parent_id == first_id
    assert ledger2.get_leaf_id("roundtrip-v1") == new_entry.id


def test_round_trip_v2_to_v3_branching(tmp_path: Path) -> None:
    header = {
        "type": "session",
        "version": 2,
        "id": "branch-parent-v2",
        "timestamp": "2026-07-01T12:00:00Z",
        "cwd": "/workspace/parent",
        "activeLeafId": "msg-2",
    }
    entry1 = {
        "id": "msg-1",
        "parentId": None,
        "type": "message",
        "timestamp": 1000.0,
        "payload": {"role": "user", "content": "parent root"},
    }
    entry2 = {
        "id": "msg-2",
        "parentId": "msg-1",
        "type": "message",
        "timestamp": 1001.0,
        "payload": {"role": "assistant", "content": "parent child"},
    }
    _write_fixture_session(tmp_path, "branch-parent-v2.jsonl", [header, entry1, entry2])

    ledger = TomeLedger(tmp_path)
    branched_meta = ledger.create_branched_tome(
        parent_tome_id="branch-parent-v2",
        cwd="/workspace/parent",
        fork_from_leaf_id="msg-1",
    )

    branched_entries = ledger.get_entries(branched_meta.id)
    assert len(branched_entries) == 1
    assert branched_entries[0].id == "msg-1"

    # Verify the branched file is written in valid v3 format
    branched_file = ledger.tome_file(branched_meta.id)
    with branched_file.open("r", encoding="utf-8") as f:
        first_line = json.loads(f.readline())
        assert first_line["version"] == 3


def test_iter_and_read_tail_with_v1_and_v2(tmp_path: Path) -> None:
    header = {
        "type": "session",
        "id": "iter-v1",
        "timestamp": "2026-07-01T12:00:00Z",
        "cwd": "/workspace/iter",
    }
    entries = [
        {
            "type": "message",
            "timestamp": 1000.0 + i,
            "payload": {"role": "user", "content": f"msg-{i}"},
        }
        for i in range(5)
    ]
    _write_fixture_session(tmp_path, "iter-v1.jsonl", [header, *entries])

    ledger = TomeLedger(tmp_path)

    # Test iter_tome_entries
    streamed = list(ledger.iter_tome_entries("iter-v1"))
    assert len(streamed) == 5
    assert streamed[0].parent_id is None
    for i in range(1, 5):
        assert streamed[i].parent_id == streamed[i - 1].id

    # Test read_last_n_entries
    tail = ledger.read_last_n_entries("iter-v1", limit=2)
    assert len(tail) == 2
    assert tail[0].payload["content"] == "msg-3"
    assert tail[1].payload["content"] == "msg-4"
    assert tail[1].parent_id == tail[0].id
