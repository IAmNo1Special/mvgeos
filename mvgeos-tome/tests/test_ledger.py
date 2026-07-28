import tempfile
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntry, TomeEntryType, TomeMetadata


def test_ledger_create_tome() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = TomeLedger(Path(tmpdir))
        meta = TomeMetadata(
            id="tome-1",
            created_at="2026-07-29T00:00:00Z",
            cwd="/home/user/project",
        )
        result = ledger.create_tome(meta)
        assert result.id == "tome-1"


def test_ledger_append_and_get_entries() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = TomeLedger(Path(tmpdir))
        meta = TomeMetadata(
            id="tome-2",
            created_at="2026-07-29T00:00:00Z",
            cwd="/home/user/project",
        )
        ledger.create_tome(meta)
        entry = TomeEntry(
            id="entry-1",
            parent_id=None,
            type=TomeEntryType.INVOCATION,
            timestamp=0.0,
            payload={"text": "hello"},
        )
        ledger.append("tome-2", entry)
        entries = ledger.get_entries("tome-2")
        assert len(entries) == 1
        assert entries[0].id == "entry-1"
