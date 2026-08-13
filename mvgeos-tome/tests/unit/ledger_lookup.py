from __future__ import annotations

import tempfile
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger


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


