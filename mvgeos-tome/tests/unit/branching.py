from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger


def _ledger(tmp: str) -> TomeLedger:
    return TomeLedger(Path(tmp))


class TestParentIdAndBranching:
    def test_persists_parent_id_in_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")
            e1 = ledger.append_message(tome.id, "user", "hello", parent_id=None)
            ledger.append_leaf(tome.id, e1.id)
            e2 = ledger.append_message(tome.id, "assistant", "hi", parent_id=e1.id)
            ledger.append_leaf(tome.id, e2.id)

            tome_file = ledger.tome_file(tome.id)
            lines = [
                json.loads(line)
                for line in tome_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            # Line 0 is header
            assert lines[0]["type"] == "session"

            # Find message entries
            messages = [entry for entry in lines if entry.get("type") == "message"]
            assert len(messages) == 2
            assert messages[0]["id"] == e1.id
            assert messages[0]["parentId"] is None
            assert messages[1]["id"] == e2.id
            assert messages[1]["parentId"] == e1.id

    def test_create_branched_tome_copies_ancestor_entries_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")

            e1 = ledger.append_message(
                tome.id, "user", "turn 1 request", parent_id=None
            )
            ledger.append_leaf(tome.id, e1.id)

            e2 = ledger.append_message(
                tome.id, "assistant", "turn 1 response", parent_id=e1.id
            )
            ledger.append_leaf(tome.id, e2.id)

            e3 = ledger.append_message(
                tome.id, "user", "turn 2 request", parent_id=e2.id
            )
            ledger.append_leaf(tome.id, e3.id)

            e4 = ledger.append_message(
                tome.id, "assistant", "turn 2 response", parent_id=e3.id
            )
            ledger.append_leaf(tome.id, e4.id)

            # Fork from e2
            forked = ledger.create_branched_tome(
                parent_tome_id=tome.id,
                cwd="/tmp",
                fork_from_leaf_id=e2.id,
            )

            forked_entries = ledger.get_entries(forked.id)
            entry_ids = [e.id for e in forked_entries]

            # Fork should include e1 and e2, but NOT e3 or e4
            assert entry_ids == [e1.id, e2.id]
            assert forked.parent_tome_id == tome.id
            assert forked.active_leaf_id == e2.id

    def test_get_entries_for_context_reconstructs_ancestor_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")

            e1 = ledger.append_message(tome.id, "user", "1", parent_id=None)
            ledger.append_leaf(tome.id, e1.id)

            e2 = ledger.append_message(tome.id, "assistant", "2", parent_id=e1.id)
            ledger.append_leaf(tome.id, e2.id)

            # Branch A
            e3a = ledger.append_message(tome.id, "user", "3a", parent_id=e2.id)
            ledger.append_leaf(tome.id, e3a.id)

            e4a = ledger.append_message(tome.id, "assistant", "4a", parent_id=e3a.id)
            ledger.append_leaf(tome.id, e4a.id)

            # Branch B branching from e2
            e3b = ledger.append_message(tome.id, "user", "3b", parent_id=e2.id)
            ledger.append_leaf(tome.id, e3b.id)

            e4b = ledger.append_message(tome.id, "assistant", "4b", parent_id=e3b.id)
            ledger.append_leaf(tome.id, e4b.id)

            # Context for 4a should be: e1 -> e2 -> e3a -> e4a
            context_a = ledger.get_entries_for_context(tome.id, leaf_id=e4a.id)
            assert [e.id for e in context_a] == [e1.id, e2.id, e3a.id, e4a.id]

            # Context for 4b should be: e1 -> e2 -> e3b -> e4b
            context_b = ledger.get_entries_for_context(tome.id, leaf_id=e4b.id)
            assert [e.id for e in context_b] == [e1.id, e2.id, e3b.id, e4b.id]

    def test_get_leaf_id_falls_back_to_metadata_active_leaf_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome("/tmp")

            e1 = ledger.append_message(tome.id, "user", "turn 1", parent_id=None)
            ledger.append_leaf(tome.id, e1.id)

            forked = ledger.create_branched_tome(
                parent_tome_id=tome.id,
                cwd="/tmp",
                fork_from_leaf_id=e1.id,
            )

            # Newly forked tome has no LEAF entry yet, but metadata has
            # active_leaf_id=e1.id
            assert ledger.get_leaf_id(forked.id) == e1.id

    def test_create_and_branched_tome_stores_and_overrides_session_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = _ledger(tmp)
            tome = ledger.create_tome(
                "/tmp",
                model="anthropic/claude-3.5-sonnet",
                contemplation_level="high",
                spells=["bash", "read_file"],
            )
            assert tome.model == "anthropic/claude-3.5-sonnet"
            assert tome.contemplation_level == "high"
            assert tome.spells == ["bash", "read_file"]

            # Verify persisted header
            meta = ledger.open_tome(tome.id)
            assert meta is not None
            assert meta.model == "anthropic/claude-3.5-sonnet"
            assert meta.contemplation_level == "high"
            assert meta.spells == ["bash", "read_file"]

            # Fork inheriting parent config
            forked1 = ledger.create_branched_tome(
                parent_tome_id=tome.id,
                cwd="/tmp",
            )
            assert forked1.model == "anthropic/claude-3.5-sonnet"
            assert forked1.contemplation_level == "high"
            assert forked1.spells == ["bash", "read_file"]

            # Fork overriding config
            forked2 = ledger.create_branched_tome(
                parent_tome_id=tome.id,
                cwd="/tmp",
                model="openai/gpt-4o",
                contemplation_level="low",
                spells=["bash"],
            )
            assert forked2.model == "openai/gpt-4o"
            assert forked2.contemplation_level == "low"
            assert forked2.spells == ["bash"]
