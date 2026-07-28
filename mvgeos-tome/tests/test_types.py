from mvgeos_tome.types import (
    TomeEntry,
    TomeEntryType,
    TomeMetadata,
)


def test_tome_entry_has_required_fields() -> None:
    entry = TomeEntry(
        id="entry-1",
        parent_id=None,
        type=TomeEntryType.INVOCATION,
        timestamp=0.0,
        payload={},
    )
    assert entry.id == "entry-1"
    assert entry.type == TomeEntryType.INVOCATION


def test_tome_metadata_has_required_fields() -> None:
    meta = TomeMetadata(
        id="tome-1",
        created_at="2026-07-29T00:00:00Z",
        cwd="/home/user/project",
        parent_tome_id=None,
        active_leaf_id=None,
    )
    assert meta.id == "tome-1"
    assert meta.cwd == "/home/user/project"
