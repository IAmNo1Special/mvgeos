from __future__ import annotations

import json
import tracemalloc
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger


def _create_large_session_file(
    tome_dir: Path, tome_id: str, target_size_mb: int = 100
) -> tuple[Path, int]:
    tome_file = tome_dir / f"{tome_id}.jsonl"
    header = {
        "type": "session",
        "version": 1,
        "id": tome_id,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "cwd": "/tmp",
        "schema_version": "1.0",
    }
    entries_per_batch = 1000
    batch_lines = []
    for i in range(entries_per_batch):
        entry_dict = {
            "id": f"batch-{i:04d}",
            "parentId": None,
            "type": "message",
            "timestamp": 1000.0 + i,
            "payload": {"role": "user", "content": "x" * 1000},
        }
        batch_lines.append(json.dumps(entry_dict) + "\n")
    batch_str = "".join(batch_lines)
    batch_bytes = batch_str.encode("utf-8")
    batches_needed = (target_size_mb * 1024 * 1024) // len(batch_bytes) + 1

    total_entries = 0
    with tome_file.open("wb") as f:
        f.write((json.dumps(header) + "\n").encode("utf-8"))
        for _ in range(batches_needed):
            f.write(batch_bytes)
            total_entries += entries_per_batch

    tail_entry = {
        "id": "final-tail-entry",
        "parentId": "batch-0999",
        "type": "message",
        "timestamp": 99999.0,
        "payload": {"role": "assistant", "content": "final tail marker"},
    }
    with tome_file.open("ab") as f:
        f.write((json.dumps(tail_entry) + "\n").encode("utf-8"))
        total_entries += 1

    return tome_file, total_entries


def test_streaming_iteration_memory_is_bounded_on_100mb_session(
    tmp_path: Path,
) -> None:
    tome_id = "large-session-stream"
    tome_file, total_entries = _create_large_session_file(
        tmp_path, tome_id, target_size_mb=100
    )
    assert tome_file.stat().st_size >= 100 * 1024 * 1024

    ledger = TomeLedger(tmp_path)

    tracemalloc.start()
    tracemalloc.reset_peak()

    streamed_count = 0
    for _ in ledger.iter_tome_entries(tome_id):
        streamed_count += 1

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert streamed_count == total_entries
    # Bounded memory: streaming 100MB must allocate under 5MB peak
    assert peak < 5 * 1024 * 1024, (
        f"Peak memory {peak / (1024 * 1024):.2f}MB exceeded 5MB bound"
    )


def test_tail_reader_memory_is_bounded_on_100mb_session(
    tmp_path: Path,
) -> None:
    tome_id = "large-session-tail"
    tome_file, _total_entries = _create_large_session_file(
        tmp_path, tome_id, target_size_mb=100
    )
    assert tome_file.stat().st_size >= 100 * 1024 * 1024

    ledger = TomeLedger(tmp_path)

    tracemalloc.start()
    tracemalloc.reset_peak()

    tail = ledger.read_last_n_entries(tome_id, limit=10)

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(tail) == 10
    assert tail[-1].id == "final-tail-entry"
    assert tail[-1].payload["content"] == "final tail marker"
    # Bounded memory: tail reader must allocate under 1MB peak
    assert peak < 1 * 1024 * 1024, (
        f"Peak memory {peak / (1024 * 1024):.2f}MB exceeded 1MB bound"
    )


def test_verify_integrity_memory_is_bounded_on_100mb_session(
    tmp_path: Path,
) -> None:
    tome_id = "large-session-audit"
    tome_file, total_entries = _create_large_session_file(
        tmp_path, tome_id, target_size_mb=100
    )
    assert tome_file.stat().st_size >= 100 * 1024 * 1024

    ledger = TomeLedger(tmp_path)

    tracemalloc.start()
    tracemalloc.reset_peak()

    report = ledger.verify_integrity(tome_id)

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert report.valid is True
    assert report.valid_entries_count == total_entries
    assert peak < 5 * 1024 * 1024, (
        f"Peak memory {peak / (1024 * 1024):.2f}MB exceeded 5MB bound"
    )
