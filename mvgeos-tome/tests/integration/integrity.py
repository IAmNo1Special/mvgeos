from __future__ import annotations

from pathlib import Path

from mvgeos_tome.ledger import TomeLedger


def test_session_lifecycle_with_integrity_audit_and_crash_recovery(
    tmp_path: Path,
) -> None:
    ledger = TomeLedger(tmp_path)

    # 1. Create and populate a tome session
    meta = ledger.create_tome("/workspace/myproject")
    m1 = ledger.append_message(meta.id, "user", "Implement feature X")
    l1 = ledger.append_leaf(meta.id, m1.id)
    m2 = ledger.append_message(
        meta.id, "assistant", "Sure, starting now", parent_id=m1.id
    )
    ledger.append_leaf(meta.id, m2.id)

    # 2. Initial integrity audit
    report = ledger.verify_integrity(meta.id)
    assert report.valid is True
    assert len(report.issues) == 0
    assert report.valid_entries_count == 4  # 2 messages, 2 leaves

    # 3. Simulate mid-write power loss / process crash by appending incomplete entry
    tome_file = ledger.tome_file(meta.id)
    with tome_file.open("a", encoding="utf-8") as f:
        f.write(f'{{"id": "partially_written", "parentId": "{m2.id}", "type": "messa')

    # Invalidate ledger cache to force disk read
    ledger._invalidate_cache(meta.id)

    # 4. Audit detects damaged line with precise line number
    corrupt_report = ledger.verify_integrity(meta.id)
    assert corrupt_report.valid is False
    assert len(corrupt_report.issues) == 1
    assert corrupt_report.issues[0].line_number == 6
    assert corrupt_report.valid_entries_count == 4
    assert corrupt_report.total_lines == 6

    # 5. Read operations recover all uncorrupted entries without crashing
    recovered_entries = ledger.get_entries(meta.id)
    assert len(recovered_entries) == 4
    assert [e.id for e in recovered_entries[:2]] == [m1.id, l1.id]
    assert recovered_entries[2].id == m2.id

    # 6. New TomeLedger instance successfully opens session header
    new_ledger = TomeLedger(tmp_path)
    loaded_meta = new_ledger.open_tome(meta.id)
    assert loaded_meta is not None
    assert loaded_meta.id == meta.id
