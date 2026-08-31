from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from mvgeos_tome.ledger import TomeLedger


def _write_tome_file(tome_dir: Path, tome_id: str, entries_data: list[dict]) -> Path:
    """Write a tome jsonl file directly to disk (bypassing the ledger)."""
    tome_file = tome_dir / f"{tome_id}.jsonl"
    header = {
        "type": "session",
        "version": 3,
        "id": tome_id,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "cwd": "/tmp",
        "schema_version": "1.0",
    }
    with tome_file.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for entry in entries_data:
            f.write(json.dumps(entry) + "\n")
    return tome_file


class TestLazyLoadingNoEagerEntryParsing:
    def test_init_does_not_parse_entry_lines(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            entries = [
                {
                    "id": "entry-1",
                    "parentId": None,
                    "type": "message",
                    "timestamp": time.time(),
                    "payload": {"role": "user", "content": "hello"},
                },
                {
                    "id": "entry-2",
                    "parentId": "entry-1",
                    "type": "message",
                    "timestamp": time.time(),
                    "payload": {"role": "assistant", "content": "hi"},
                },
            ]
            _write_tome_file(tome_dir, "tome-1", entries)

            ledger = TomeLedger(tome_dir)

            metas = ledger.list_tomes()
            assert len(metas) == 1
            assert metas[0].id == "tome-1"

            assert ledger._entries_cache.get(
                "tome-1"
            ) is None or not ledger._entries_cache.get("tome-1", {})

    def test_list_tomes_reads_only_header_line(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            entries = [
                {
                    "id": "a",
                    "parentId": None,
                    "type": "message",
                    "timestamp": time.time(),
                    "payload": {"role": "user", "content": "hello"},
                },
            ]
            _write_tome_file(tome_dir, "tome-a", entries)

            with patch.object(TomeLedger, "_read_tome_entries") as mock_read:
                TomeLedger(tome_dir)
                mock_read.assert_not_called()

    def test_init_with_many_archived_tomes_is_fast(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            for i in range(200):
                _write_tome_file(tome_dir, f"tome-{i:04d}", [])

            start = time.perf_counter()
            ledger = TomeLedger(tome_dir)
            elapsed = time.perf_counter() - start

            assert elapsed < 2.5, f"Init took {elapsed:.3f}s for 200 tomes"
            assert len(ledger.list_tomes()) == 200

    def test_get_entries_lazy_loads_only_accessed_tome(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            _write_tome_file(
                tome_dir,
                "tome-a",
                [
                    {
                        "id": "a1",
                        "parentId": None,
                        "type": "message",
                        "timestamp": time.time(),
                        "payload": {},
                    }
                ],
            )
            _write_tome_file(
                tome_dir,
                "tome-b",
                [
                    {
                        "id": "b1",
                        "parentId": None,
                        "type": "message",
                        "timestamp": time.time(),
                        "payload": {},
                    }
                ],
            )

            ledger = TomeLedger(tome_dir)

            with patch.object(
                TomeLedger, "_read_tome_entries_from_disk"
            ) as mock_read_disk:
                mock_read_disk.return_value = []
                ledger.get_entries("tome-a")
                mock_read_disk.assert_called_once()
                called_tomes = [call.args[0] for call in mock_read_disk.call_args_list]
                assert "tome-a" in called_tomes

    def test_entries_cache_is_bounded_lru(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            for i in range(10):
                _write_tome_file(tome_dir, f"tome-{i:02d}", [])

            ledger = TomeLedger(tome_dir)

            max_cache = ledger._MAX_CACHE_SIZE
            assert max_cache > 0

            for i in range(10):
                ledger.get_entries(f"tome-{i:02d}")

            cached = ledger._entries_cache
            assert len(cached) <= max_cache


class TestCacheEviction:
    def test_lru_evicts_least_recently_used(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            for i in range(40):
                _write_tome_file(tome_dir, f"tome-{i:04d}", [])

            ledger = TomeLedger(tome_dir)
            max_cache = ledger._MAX_CACHE_SIZE

            for i in range(max_cache):
                ledger.get_entries(f"tome-{i:04d}")
            assert len(ledger._entries_cache) == max_cache

            ledger.get_entries("tome-0000")
            ledger.get_entries("tome-0000")

            for i in range(max_cache, max_cache + 5):
                ledger.get_entries(f"tome-{i:04d}")

            assert len(ledger._entries_cache) <= max_cache
            assert "tome-0000" in ledger._entries_cache

    def test_append_invalidates_entry_cache(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            ledger = TomeLedger(tome_dir)
            t = ledger.create_tome("/tmp")
            ledger.append_message(t.id, "user", "first")

            entries = ledger.get_entries(t.id)
            assert len(entries) == 1
            assert t.id in ledger._entries_cache

            ledger.append_message(t.id, "user", "second")

            cached = ledger._entries_cache.get(t.id)
            assert cached is None


class TestScopedIndexAccess:
    def test_get_entry_scopes_to_tome(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            tome = TomeLedger(tome_dir)
            tome_a = tome.create_tome("/a")
            tome_b = tome.create_tome("/b")
            entry_b = tome.append_message(tome_b.id, "user", "in B")

            assert tome.get_entry(tome_a.id, entry_b.id) is None
            assert tome.get_entry(tome_b.id, entry_b.id) is not None

    def test_get_entries_filtered_by_type(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            ledger = TomeLedger(tome_dir)
            t = ledger.create_tome("/tmp")
            e1 = ledger.append_message(t.id, "user", "hello")
            ledger.append_leaf(t.id, e1.id)

            leaves = ledger.get_entries(t.id, entry_type=None)
            assert len(leaves) == 2

            from mvgeos_tome.types import TomeEntryType

            leaf_only = ledger.get_entries(t.id, entry_type=TomeEntryType.LEAF)
            assert len(leaf_only) == 1

    def test_get_entries_for_context_reconstructs_ancestors(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tome_dir = Path(tmp)
            ledger = TomeLedger(tome_dir)
            t = ledger.create_tome("/tmp")

            e1 = ledger.append_message(t.id, "user", "1", parent_id=None)
            ledger.append_leaf(t.id, e1.id)
            e2 = ledger.append_message(t.id, "assistant", "2", parent_id=e1.id)
            ledger.append_leaf(t.id, e2.id)
            e3 = ledger.append_message(t.id, "user", "3", parent_id=e2.id)
            ledger.append_leaf(t.id, e3.id)

            context = ledger.get_entries_for_context(t.id, leaf_id=e3.id)
            assert [e.id for e in context] == [e1.id, e2.id, e3.id]
