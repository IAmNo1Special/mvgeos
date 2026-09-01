from mvgeos_tome.types import (
    TomeEntry,
    TomeEntryType,
    TomeIntegrityIssue,
    TomeIntegrityReport,
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
        model="openai/gpt-4o",
        contemplation_level="high",
        spells=["bash", "read_file"],
    )
    assert meta.id == "tome-1"
    assert meta.cwd == "/home/user/project"
    assert meta.model == "openai/gpt-4o"
    assert meta.contemplation_level == "high"
    assert meta.spells == ["bash", "read_file"]


def test_tome_integrity_report_properties() -> None:
    issue = TomeIntegrityIssue(line_number=2, message="Bad line", raw_line="bad")
    assert issue.line_number == 2
    assert issue.message == "Bad line"
    assert issue.raw_line == "bad"

    report_valid = TomeIntegrityReport(valid=True, tome_id="tome-1")
    assert bool(report_valid) is True
    assert len(report_valid.issues) == 0

    report_invalid = TomeIntegrityReport(valid=False, tome_id="tome-1", issues=[issue])
    assert bool(report_invalid) is False
    assert len(report_invalid.issues) == 1
    assert report_invalid.issues[0] == issue
