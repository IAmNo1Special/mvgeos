from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeVersionError


def _ledger(tmp: str) -> TomeLedger:
    return TomeLedger(Path(tmp))


class TestGetEntry:
    def test_finds_an_appended_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")
            entry = ledger.append_message(tome.id, "user", "hello")

            found = ledger.get_entry(tome.id, entry.id)

            assert found is not None
            assert found.id == entry.id

    def test_returns_none_for_unknown_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")

            assert ledger.get_entry(tome.id, "nope") is None

    def test_does_not_leak_entries_across_tomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_a = ledger.create_tome("/a")
            tome_b = ledger.create_tome("/b")
            entry_b = ledger.append_message(tome_b.id, "user", "in B")

            # The entry belongs to B, so asking A for it must miss.
            assert ledger.get_entry(tome_a.id, entry_b.id) is None
            assert ledger.get_entry(tome_b.id, entry_b.id) is not None


class TestGetLeafId:
    def test_returns_none_before_any_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")
            ledger.append_message(tome.id, "user", "hello")

            assert ledger.get_leaf_id(tome.id) is None

    def test_returns_the_target_of_the_latest_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")
            entry = ledger.append_message(tome.id, "user", "hello")
            ledger.append_leaf(tome.id, entry.id)

            assert ledger.get_leaf_id(tome.id) == entry.id

    def test_advances_with_each_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")
            first = ledger.append_message(tome.id, "user", "one")
            ledger.append_leaf(tome.id, first.id)
            second = ledger.append_message(tome.id, "user", "two")
            ledger.append_leaf(tome.id, second.id)

            assert ledger.get_leaf_id(tome.id) == second.id

    def test_does_not_leak_leaves_across_tomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_a = ledger.create_tome("/a")
            tome_b = ledger.create_tome("/b")
            entry_b = ledger.append_message(tome_b.id, "user", "in B")
            ledger.append_leaf(tome_b.id, entry_b.id)

            assert ledger.get_leaf_id(tome_a.id) is None
            assert ledger.get_leaf_id(tome_b.id) == entry_b.id


class TestOpenTomePrefixLookup:
    def test_open_tome_resolves_unique_short_id_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_id = "098b2ee4a1b2c3d4e5f6789012345678"
            tome = ledger.create_tome("/tmp", tome_id=tome_id)
            short_id = "098b2ee4"

            resolved = ledger.open_tome(short_id)

            assert resolved is not None
            assert resolved.id == tome.id

    def test_open_tome_exact_match_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_exact = ledger.create_tome("/tmp", tome_id="098b2ee4")
            ledger.create_tome("/tmp", tome_id="098b2ee4a1b2c3d4e5f6789012345678")

            resolved = ledger.open_tome("098b2ee4")

            assert resolved is not None
            assert resolved.id == tome_exact.id

    def test_open_tome_returns_none_on_ambiguous_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            ledger.create_tome("/tmp", tome_id="098b2ee4a1b2c3d4")
            ledger.create_tome("/tmp", tome_id="098b2ee4e5f67890")

            assert ledger.open_tome("098b2ee4") is None

    def test_open_tome_returns_none_on_unknown_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            ledger.create_tome("/tmp", tome_id="098b2ee4a1b2c3d4")

            assert ledger.open_tome("deadbeef") is None

    def test_open_tome_returns_none_on_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            ledger.create_tome("/tmp", tome_id="098b2ee4a1b2c3d4")

            assert ledger.open_tome("") is None

    def test_open_tome_case_insensitive_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_id = "098b2ee4a1b2c3d4e5f6789012345678"
            tome = ledger.create_tome("/tmp", tome_id=tome_id)

            resolved = ledger.open_tome("098B2EE4")

            assert resolved is not None
            assert resolved.id == tome.id

    def test_open_tome_raw_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_id = "098b2ee4a1b2c3d4e5f6789012345678"
            tome = ledger.create_tome("/tmp", tome_id=tome_id)
            raw_path = ledger.tome_file(tome_id)

            resolved = ledger.open_tome(str(raw_path))

            assert resolved is not None
            assert resolved.id == tome.id

    def test_append_leaf_with_short_id_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_id = "098b2ee4a1b2c3d4e5f6789012345678"
            ledger.create_tome("/tmp", tome_id=tome_id)
            msg = ledger.append_message("098b2ee4", "user", "hello")
            ledger.append_leaf("098b2ee4", msg.id)

            assert ledger.get_leaf_id("098b2ee4") == msg.id

    def test_create_branched_tome_with_short_id_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_id = "098b2ee4a1b2c3d4e5f6789012345678"
            tome = ledger.create_tome("/tmp", tome_id=tome_id)
            msg = ledger.append_message("098b2ee4", "user", "hello")
            ledger.append_leaf("098b2ee4", msg.id)

            forked = ledger.create_branched_tome(
                "098b2ee4", "/tmp", fork_from_leaf_id=msg.id
            )
            assert forked.parent_tome_id == tome.id


class TestLedgerVersionHandling:
    def test_open_tome_unsupported_version_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome_file = Path(tmp) / "future-5.jsonl"
            tome_file.write_text(
                '{"type":"session","version":5,"id":"future-5","timestamp":"2026-01-01T00:00:00Z","cwd":"/tmp"}\n',
                encoding="utf-8",
            )
            with pytest.raises(TomeVersionError) as exc_info:
                ledger.open_tome("future-5")
            assert exc_info.value.version == 5

    def test_load_tome_headers_ignores_unsupported_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            valid_file = Path(tmp) / "valid-1.jsonl"
            valid_file.write_text(
                '{"type":"session","version":1,"id":"valid-1","timestamp":"2026-01-01T00:00:00Z","cwd":"/tmp"}\n',
                encoding="utf-8",
            )
            future_file = Path(tmp) / "future-99.jsonl"
            future_file.write_text(
                '{"type":"session","version":99,"id":"future-99","timestamp":"2026-01-01T00:00:00Z","cwd":"/tmp"}\n',
                encoding="utf-8",
            )
            ledger = _ledger(tmp)
            tomes = ledger.list_tomes()
            assert len(tomes) == 1
            assert tomes[0].id == "valid-1"

    def test_open_recent_skips_incompatible_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            future_file = Path(tmp) / "future-recent.jsonl"
            future_file.write_text(
                '{"type":"session","version":4,"id":"future-recent","timestamp":"2026-01-01T00:00:00Z","cwd":"/workspace/target"}\n',
                encoding="utf-8",
            )
            valid_file = Path(tmp) / "valid-recent.jsonl"
            valid_file.write_text(
                '{"type":"session","version":1,"id":"valid-recent","timestamp":"2026-01-01T00:00:00Z","cwd":"/workspace/target"}\n',
                encoding="utf-8",
            )
            ledger = _ledger(tmp)
            recent = ledger.open_recent("/workspace/target")
            assert recent is not None
            assert recent.id == "valid-recent"

    def test_load_tome_metadata_invalid_version_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "bad-version.jsonl"
            bad_file.write_text(
                '{"type":"session","version":"not-int","id":"bad-version",'
                '"timestamp":"2026-01-01T00:00:00Z","cwd":"/tmp"}\n',
                encoding="utf-8",
            )
            ledger = _ledger(tmp)
            with pytest.raises(TomeVersionError):
                ledger._load_tome_metadata("bad-version")

    def test_create_tome_from_metadata_with_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            from mvgeos_tome.types import TomeMetadata

            base_meta = TomeMetadata(
                id="custom-meta",
                created_at="2026-01-01T00:00:00Z",
                cwd="/tmp",
            )
            created = ledger.create_tome(
                base_meta,
                model="new-model",
                contemplation_level="high",
                spells=["spell1"],
            )
            assert created.model == "new-model"
            assert created.contemplation_level == "high"
            assert created.spells == ["spell1"]

    def test_append_nonexistent_tome_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            from mvgeos_tome.types import TomeEntry, TomeEntryType

            entry = TomeEntry(
                id="e1",
                parent_id=None,
                type=TomeEntryType.MESSAGE,
                timestamp=100.0,
                payload={},
            )
            with pytest.raises(ValueError, match="Tome not found"):
                ledger.append("nonexistent", entry)

    def test_append_leaf_nonexistent_tome_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            with pytest.raises(ValueError, match="Tome not found"):
                ledger.append_leaf("nonexistent", "target-id")

    def test_get_entries_for_context_max_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")
            for i in range(5):
                ledger.append_message(tome.id, "user", f"msg-{i}")
            ctx_entries = ledger.get_entries_for_context(tome.id, max_entries=2)
            assert len(ctx_entries) == 2
            assert ctx_entries[0].payload["content"] == "msg-3"
            assert ctx_entries[1].payload["content"] == "msg-4"
