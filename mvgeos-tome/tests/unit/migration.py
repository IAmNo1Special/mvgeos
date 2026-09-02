from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mvgeos_tome import TomeLedger, TomeVersionError
from mvgeos_tome.migration import (
    CURRENT_SESSION_VERSION,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
    extract_session_version,
    migrate_session_data,
)


def _write_raw_tome(tome_dir: Path, filename: str, lines: list[dict[str, Any]]) -> Path:
    target = tome_dir / filename
    with target.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return target


class TestTomeVersionError:
    def test_version_error_properties(self) -> None:
        err = TomeVersionError(4)
        assert err.version == 4
        assert "4" in str(err)

        err_custom = TomeVersionError("future", "Custom version error")
        assert err_custom.version == "future"
        assert str(err_custom) == "Custom version error"


class TestMigrationTransformations:
    def test_migrate_v1_to_v2_linear_chain(self) -> None:
        header = {
            "type": "session",
            "id": "tome-v1",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
        }
        entries = [
            {
                "type": "message",
                "timestamp": 1000.0,
                "payload": {"role": "user", "content": "hello"},
            },
            {
                "type": "message",
                "timestamp": 1001.0,
                "payload": {"role": "assistant", "content": "world"},
            },
        ]

        migrated_hdr, migrated_entries = TomeLedger._migrate_v1_to_v2(header, entries)

        assert migrated_hdr["version"] == 2
        assert len(migrated_entries) == 2

        e0 = migrated_entries[0]
        e1 = migrated_entries[1]

        assert "id" in e0
        assert len(e0["id"]) > 0
        assert e0["parentId"] is None

        assert "id" in e1
        assert len(e1["id"]) > 0
        assert e1["parentId"] == e0["id"]
        assert migrated_hdr["activeLeafId"] == e1["id"]

    def test_migrate_v1_to_v2_converts_compaction_index(self) -> None:
        header = {
            "type": "session",
            "id": "tome-v1-compaction",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
        }
        entries = [
            {
                "id": "msg-1",
                "type": "message",
                "timestamp": 1000.0,
                "payload": {"role": "user", "content": "1"},
            },
            {
                "id": "msg-2",
                "type": "message",
                "timestamp": 1001.0,
                "payload": {"role": "assistant", "content": "2"},
            },
            {
                "id": "msg-3",
                "type": "message",
                "timestamp": 1002.0,
                "payload": {"role": "user", "content": "3"},
            },
            {
                "type": "compaction",
                "timestamp": 1003.0,
                "payload": {
                    "summary": "compacted summary",
                    "manaBefore": 500,
                    "firstKeptEntryIndex": 2,
                },
            },
        ]

        migrated_hdr, migrated_entries = TomeLedger._migrate_v1_to_v2(header, entries)

        assert migrated_hdr["version"] == 2
        compaction = migrated_entries[3]
        assert compaction["payload"]["firstKeptEntryId"] == "msg-3"
        assert "firstKeptEntryIndex" not in compaction["payload"]

    def test_migrate_v2_to_v3_hook_message_to_custom(self) -> None:
        header = {
            "type": "session",
            "version": 2,
            "id": "tome-v2",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
            "activeLeafId": "e2",
        }
        entries = [
            {
                "id": "e1",
                "parentId": None,
                "type": "hookMessage",
                "timestamp": 1000.0,
                "payload": {"content": "hook output"},
            },
            {
                "id": "e2",
                "parentId": "e1",
                "type": "message",
                "timestamp": 1001.0,
                "payload": {"role": "hookMessage", "content": "legacy hook role"},
            },
        ]

        migrated_hdr, migrated_entries = TomeLedger._migrate_v2_to_v3(header, entries)

        assert migrated_hdr["version"] == 3
        assert migrated_entries[0]["type"] == "custom"
        assert migrated_entries[1]["type"] == "custom"
        assert migrated_entries[1]["payload"]["role"] == "custom"

    def test_migrate_v2_to_v3_legacy_entry_types(self) -> None:
        header = {
            "type": "session",
            "version": 2,
            "id": "tome-v2-legacy",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
        }
        entries = [
            {
                "id": "e1",
                "parentId": None,
                "type": "spellResult",
                "timestamp": 1000.0,
                "payload": {"result": "success"},
            },
            {
                "id": "e2",
                "parentId": "e1",
                "type": "modelChange",
                "timestamp": 1001.0,
                "payload": {"model": "gpt-4"},
            },
        ]

        migrated_hdr, migrated_entries = TomeLedger._migrate_v2_to_v3(header, entries)

        assert migrated_hdr["version"] == 3
        assert migrated_entries[0]["type"] == "message"
        assert migrated_entries[1]["type"] == "custom"

    def test_migrate_session_data_pipeline_full_upgrade(self) -> None:
        header = {
            "type": "session",
            "id": "v1-full",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
        }
        entries = [
            {
                "type": "message",
                "timestamp": 1000.0,
                "payload": {"role": "user", "content": "v1 user"},
            },
            {
                "type": "hookMessage",
                "timestamp": 1001.0,
                "payload": {"role": "hookMessage", "content": "v1 hook"},
            },
        ]

        migrated_hdr, migrated_entries = TomeLedger.migrate_session_data(
            header, entries
        )

        assert migrated_hdr["version"] == 3
        assert len(migrated_entries) == 2
        assert migrated_entries[0]["type"] == "message"
        assert migrated_entries[1]["type"] == "custom"
        assert migrated_entries[1]["parentId"] == migrated_entries[0]["id"]

    def test_migrate_session_data_raises_on_incompatible_future_version(self) -> None:
        header = {
            "type": "session",
            "version": 4,
            "id": "future-tome",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
        }
        with pytest.raises(TomeVersionError) as exc_info:
            TomeLedger.migrate_session_data(header, [])

        assert exc_info.value.version == 4

    def test_migrate_session_data_raises_on_invalid_version(self) -> None:
        header = {
            "type": "session",
            "version": 0,
            "id": "invalid-tome",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp/test",
        }
        with pytest.raises(TomeVersionError):
            TomeLedger.migrate_session_data(header, [])


class TestLedgerVersionHandling:
    def test_open_tome_future_version_raises(self, tmp_path: Path) -> None:
        header = {
            "type": "session",
            "version": 5,
            "id": "future-5",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp",
        }
        _write_raw_tome(tmp_path, "future-5.jsonl", [header])
        ledger = TomeLedger(tmp_path)

        with pytest.raises(TomeVersionError) as exc_info:
            ledger.open_tome("future-5")

        assert exc_info.value.version == 5

    def test_load_tome_headers_ignores_unsupported_versions(
        self, tmp_path: Path
    ) -> None:
        valid_header = {
            "type": "session",
            "version": 3,
            "id": "valid-3",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp",
        }
        future_header = {
            "type": "session",
            "version": 99,
            "id": "future-99",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/tmp",
        }
        _write_raw_tome(tmp_path, "valid-3.jsonl", [valid_header])
        _write_raw_tome(tmp_path, "future-99.jsonl", [future_header])

        ledger = TomeLedger(tmp_path)
        tomes = ledger.list_tomes()

        assert len(tomes) == 1
        assert tomes[0].id == "valid-3"

    def test_open_recent_skips_incompatible_version(self, tmp_path: Path) -> None:
        future_header = {
            "type": "session",
            "version": 4,
            "id": "future-recent",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/workspace/target",
        }
        valid_header = {
            "type": "session",
            "version": 3,
            "id": "valid-recent",
            "timestamp": "2026-01-01T00:00:00Z",
            "cwd": "/workspace/target",
        }
        _write_raw_tome(tmp_path, "future-recent.jsonl", [future_header])
        _write_raw_tome(tmp_path, "valid-recent.jsonl", [valid_header])

        ledger = TomeLedger(tmp_path)
        recent = ledger.open_recent("/workspace/target")
        assert recent is not None
        assert recent.id == "valid-recent"


class TestExtractSessionVersion:
    def test_extract_version_default_v1(self) -> None:
        assert extract_session_version({}) == 1
        assert extract_session_version({"type": "session"}) == 1

    def test_extract_version_explicit(self) -> None:
        assert extract_session_version({"version": 1}) == 1
        assert extract_session_version({"version": 2}) == 2
        assert extract_session_version({"version": 3}) == 3
        assert extract_session_version({"version": "3"}) == 3

    def test_extract_version_invalid(self) -> None:
        with pytest.raises(TomeVersionError):
            extract_session_version({"version": "invalid"})
        with pytest.raises(TomeVersionError):
            extract_session_version({"version": 0})
        with pytest.raises(TomeVersionError):
            extract_session_version({"version": -1})
        with pytest.raises(TomeVersionError):
            extract_session_version({"version": 4})

    def test_module_level_migration_functions(self) -> None:
        assert CURRENT_SESSION_VERSION == 3
        hdr, entries = _migrate_v1_to_v2(
            {"id": "t1", "type": "session"},
            [{"type": "message", "payload": {"content": "hi"}}],
        )
        assert hdr["version"] == 2
        assert entries[0]["id"] is not None

        hdr3, entries3 = _migrate_v2_to_v3(hdr, entries)
        assert hdr3["version"] == 3

        final_hdr, final_entries = migrate_session_data(
            {"id": "t2", "type": "session"},
            [{"type": "message", "payload": {"content": "direct"}}],
        )
        assert final_hdr["version"] == 3
        assert len(final_entries) == 1
