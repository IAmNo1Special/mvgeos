from __future__ import annotations

import tempfile
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.agent_session import MvgeTome


def _tome(tmp: str) -> tuple[MvgeTome, TomeLedger]:
    ledger = TomeLedger(Path(tmp))
    meta = ledger.create_tome("/tmp")
    tome = MvgeTome(ledger, meta)
    tome._started = True
    return tome, ledger


class TestLeafAdvances:
    def test_leaf_advances_on_recorded_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)

            entry = tome.record_message(role="user", content="hello")

            assert entry is not None
            assert ledger.get_leaf_id(tome.tome_id) == entry.id

    def test_leaf_tracks_the_most_recent_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)

            tome.record_message(role="user", content="one")
            second = tome.record_message(role="assistant", content="two")

            assert second is not None
            assert ledger.get_leaf_id(tome.tome_id) == second.id

    def test_metadata_active_leaf_id_is_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, _ = _tome(tmp)

            entry = tome.record_message(role="user", content="hello")

            assert entry is not None
            assert tome.metadata.active_leaf_id == entry.id

    def test_no_leaf_recorded_when_tome_not_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TomeLedger(Path(tmp))
            meta = ledger.create_tome("/tmp")
            tome = MvgeTome(ledger, meta)

            tome.record_message(role="user", content="dropped")

            assert ledger.get_leaf_id(tome.tome_id) is None

    def test_leaf_survives_reload_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, _ = _tome(tmp)
            entry = tome.record_message(role="user", content="hello")
            assert entry is not None

            reopened = TomeLedger(Path(tmp))

            assert reopened.get_leaf_id(tome.tome_id) == entry.id
