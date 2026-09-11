from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntry, TomeEntryType, TomeVersionError


def _write_raw_tome(
    tome_dir: Path, tome_id: str, entries_data: list[dict[str, Any]]
) -> Path:
    tome_file = tome_dir / f"{tome_id}.jsonl"
    header = {
        "type": "session",
        "version": 1,
        "id": tome_id,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "cwd": str(tome_dir),
        "schema_version": "1.0",
    }
    with tome_file.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for entry in entries_data:
            f.write(json.dumps(entry) + "\n")
    return tome_file


class TestIterTomeEntries:
    def test_iter_tome_entries_yields_entries_sequentially(
        self, tmp_path: Path
    ) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        m1 = ledger.append_message(tome.id, "user", "one")
        l1 = ledger.append_leaf(tome.id, m1.id)
        m2 = ledger.append_message(tome.id, "assistant", "two")

        # Force cache eviction to test disk streaming
        ledger._invalidate_cache(tome.id)

        gen = ledger.iter_tome_entries(tome.id)
        entries = list(gen)

        assert len(entries) == 3
        assert [e.id for e in entries] == [m1.id, l1.id, m2.id]
        assert entries[0].type == TomeEntryType.MESSAGE
        assert entries[1].type == TomeEntryType.LEAF
        assert entries[2].type == TomeEntryType.MESSAGE
        assert entries[0].payload["content"] == "one"

    def test_iter_tome_entries_from_cache(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        m1 = ledger.append_message(tome.id, "user", "one")

        # Populate cache via get_entries
        cached = ledger.get_entries(tome.id)
        assert len(cached) == 1
        assert tome.id in ledger._entries_cache

        entries = list(ledger.iter_tome_entries(tome.id))
        assert len(entries) == 1
        assert entries[0].id == m1.id

    def test_iter_tome_entries_skips_corrupted_lines_gracefully(
        self, tmp_path: Path
    ) -> None:
        ledger = TomeLedger(tmp_path)
        tome_id = "test-corrupt"
        entries_data = [
            {
                "id": "e1",
                "parentId": None,
                "type": "message",
                "timestamp": 100.0,
                "payload": {"content": "first"},
            },
            {
                "id": "e2",
                "parentId": "e1",
                "type": "message",
                "timestamp": 101.0,
                "payload": {"content": "second"},
            },
        ]
        tome_file = _write_raw_tome(tmp_path, tome_id, entries_data)

        # Insert corrupt lines
        with tome_file.open("a", encoding="utf-8") as f:
            f.write("not valid json\n")
            f.write('{"id": "e3", "type": "invalid_type", "timestamp": 102.0}\n')
            f.write(
                json.dumps(
                    {
                        "id": "e4",
                        "parentId": "e2",
                        "type": "message",
                        "timestamp": 103.0,
                        "payload": {"content": "third"},
                    }
                )
                + "\n"
            )

        ledger._load_tome_headers()
        streamed = list(ledger.iter_tome_entries(tome_id))
        assert [e.id for e in streamed] == ["e1", "e2", "e4"]

    def test_iter_tome_entries_empty_file_or_header_only(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        ledger._invalidate_cache(tome.id)

        assert list(ledger.iter_tome_entries(tome.id)) == []
        assert list(ledger.iter_tome_entries("non-existent-tome")) == []

    @pytest.mark.asyncio
    async def test_iter_tome_entries_async(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        m1 = ledger.append_message(tome.id, "user", "async one")
        m2 = ledger.append_message(tome.id, "assistant", "async two")
        ledger._invalidate_cache(tome.id)

        results: list[TomeEntry] = []
        async for entry in ledger.iter_tome_entries_async(tome.id):
            results.append(entry)

        assert len(results) == 2
        assert [e.id for e in results] == [m1.id, m2.id]

    def test_iter_tome_entries_unsupported_version_raises(self, tmp_path: Path) -> None:
        file_path = tmp_path / "v9.jsonl"
        file_path.write_text(
            '{"type": "session", "version": 9, "id": "v9", '
            '"timestamp": "2026-01-01T00:00:00Z", "cwd": "/tmp"}\n',
            encoding="utf-8",
        )
        ledger = TomeLedger(tmp_path)
        with pytest.raises(TomeVersionError):
            list(ledger.iter_tome_entries("v9"))

    def test_iter_tome_entries_invalid_version_raises(self, tmp_path: Path) -> None:
        file_path = tmp_path / "bad-ver.jsonl"
        file_path.write_text(
            '{"type": "session", "version": "not-a-num", "id": "bad-ver", '
            '"timestamp": "2026-01-01T00:00:00Z", "cwd": "/tmp"}\n',
            encoding="utf-8",
        )
        ledger = TomeLedger(tmp_path)
        with pytest.raises(TomeVersionError):
            list(ledger.iter_tome_entries("bad-ver"))

    def test_iter_tome_entries_header_invalid_json(self, tmp_path: Path) -> None:
        file_path = tmp_path / "bad-json.jsonl"
        file_path.write_text("NOT_JSON\n", encoding="utf-8")
        ledger = TomeLedger(tmp_path)
        assert list(ledger.iter_tome_entries("bad-json")) == []

    def test_iter_tome_entries_header_not_session(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not-session.jsonl"
        file_path.write_text('{"type": "other"}\n', encoding="utf-8")
        ledger = TomeLedger(tmp_path)
        assert list(ledger.iter_tome_entries("not-session")) == []

    def test_iter_tome_entries_entry_not_object(self, tmp_path: Path) -> None:
        file_path = tmp_path / "entry-string.jsonl"
        file_path.write_text(
            '{"type": "session", "version": 1, "id": "entry-string", '
            '"timestamp": "2026-01-01T00:00:00Z", "cwd": "/tmp"}\n'
            '"just-a-string"\n\n',
            encoding="utf-8",
        )
        ledger = TomeLedger(tmp_path)
        assert list(ledger.iter_tome_entries("entry-string")) == []


class TestReadLastNEntries:
    def test_read_last_n_entries_bounded_slice(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        for i in range(10):
            ledger.append_message(tome.id, "user", f"msg-{i}")

        ledger._invalidate_cache(tome.id)

        tail = ledger.read_last_n_entries(tome.id, limit=3)
        assert len(tail) == 3
        assert [e.payload["content"] for e in tail] == [
            "msg-7",
            "msg-8",
            "msg-9",
        ]

    def test_read_last_n_entries_limit_greater_than_total(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        m1 = ledger.append_message(tome.id, "user", "msg-0")
        m2 = ledger.append_message(tome.id, "user", "msg-1")

        ledger._invalidate_cache(tome.id)

        tail = ledger.read_last_n_entries(tome.id, limit=100)
        assert len(tail) == 2
        assert [e.id for e in tail] == [m1.id, m2.id]

    def test_read_last_n_entries_zero_or_negative_limit(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        ledger.append_message(tome.id, "user", "msg-0")

        assert ledger.read_last_n_entries(tome.id, limit=0) == []
        assert ledger.read_last_n_entries(tome.id, limit=-5) == []

    def test_read_last_n_entries_from_cache(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        for i in range(5):
            ledger.append_message(tome.id, "user", f"cached-{i}")

        # Populate cache
        ledger.get_entries(tome.id)
        assert tome.id in ledger._entries_cache

        tail = ledger.read_last_n_entries(tome.id, limit=2)
        assert len(tail) == 2
        assert [e.payload["content"] for e in tail] == ["cached-3", "cached-4"]

    def test_read_last_n_entries_across_multi_chunk_boundaries(
        self, tmp_path: Path
    ) -> None:
        ledger = TomeLedger(tmp_path)
        tome_id = "large-tail-test"
        entries_data = [
            {
                "id": f"entry-{i:05d}",
                "parentId": f"entry-{i - 1:05d}" if i > 0 else None,
                "type": "message",
                "timestamp": 1000.0 + i,
                "payload": {
                    "role": "user",
                    "content": f"data-{i:05d}-" + "x" * 200,
                },
            }
            for i in range(1000)
        ]
        _write_raw_tome(tmp_path, tome_id, entries_data)
        ledger._load_tome_headers()

        tail = ledger.read_last_n_entries(tome_id, limit=25)
        assert len(tail) == 25
        assert tail[0].id == "entry-00975"
        assert tail[-1].id == "entry-00999"

    def test_read_last_n_entries_skips_corrupted_lines(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome_id = "tail-corrupt"
        entries_data = [
            {
                "id": "e1",
                "parentId": None,
                "type": "message",
                "timestamp": 1.0,
                "payload": {"msg": "1"},
            },
            {
                "id": "e2",
                "parentId": "e1",
                "type": "message",
                "timestamp": 2.0,
                "payload": {"msg": "2"},
            },
        ]
        tome_file = _write_raw_tome(tmp_path, tome_id, entries_data)

        with tome_file.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "id": "e3",
                        "parentId": "e2",
                        "type": "message",
                        "timestamp": 3.0,
                        "payload": {"msg": "3"},
                    }
                )
                + "\n"
            )
            f.write("corrupted json\n")
            f.write(
                json.dumps(
                    {
                        "id": "e4",
                        "parentId": "e3",
                        "type": "message",
                        "timestamp": 4.0,
                        "payload": {"msg": "4"},
                    }
                )
                + "\n"
            )

        ledger._load_tome_headers()
        tail = ledger.read_last_n_entries(tome_id, limit=3)
        assert len(tail) == 3
        assert [e.id for e in tail] == ["e2", "e3", "e4"]

    def test_read_last_n_entries_continues_seeking_past_trailing_corrupt_lines(
        self, tmp_path: Path
    ) -> None:
        ledger = TomeLedger(tmp_path)
        tome_id = "trailing-corrupt"
        entries_data = [
            {
                "id": f"valid-{i}",
                "parentId": None,
                "type": "message",
                "timestamp": float(i),
                "payload": {"msg": str(i)},
            }
            for i in range(5)
        ]
        tome_file = _write_raw_tome(tmp_path, tome_id, entries_data)

        # Append several corrupt / empty / malformed lines at the very end
        with tome_file.open("a", encoding="utf-8") as f:
            for _ in range(10):
                f.write("not valid json\n\n")

        ledger._load_tome_headers()
        tail = ledger.read_last_n_entries(tome_id, limit=3)
        assert len(tail) == 3
        assert [e.id for e in tail] == ["valid-2", "valid-3", "valid-4"]

    def test_read_last_n_entries_prefix_resolution(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        long_id = "0123456789abcdef0123456789abcdef"
        ledger.create_tome(str(tmp_path), tome_id=long_id)
        ledger.append_message(long_id, "user", "msg1")
        ledger.append_message(long_id, "user", "msg2")
        ledger._invalidate_cache(long_id)

        tail = ledger.read_last_n_entries("01234567", limit=1)
        assert len(tail) == 1
        assert tail[0].payload["content"] == "msg2"

    @pytest.mark.asyncio
    async def test_read_last_n_entries_async(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        tome = ledger.create_tome(str(tmp_path))
        ledger.append_message(tome.id, "user", "async-1")
        ledger.append_message(tome.id, "user", "async-2")
        ledger._invalidate_cache(tome.id)

        tail = await ledger.read_last_n_entries_async(tome.id, limit=1)
        assert len(tail) == 1
        assert tail[0].payload["content"] == "async-2"
