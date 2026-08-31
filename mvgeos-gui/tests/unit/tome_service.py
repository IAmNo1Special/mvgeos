"""Unit tests for TomeService and related utilities in mvgeos-gui."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mvgeos_tome.ledger import TomeLedger

from mvgeos_gui.git_workspace import resolve_git_branch
from mvgeos_gui.tome_service import (
    TomeListEntry,
    TomeService,
    format_relative_time,
)


def _init_git_repo(repo_path: Path, branch: str) -> None:
    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    (repo_path / "README.md").write_text("test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )


class TestFormatRelativeTime:
    def test_now_within_a_minute(self) -> None:
        ts = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        assert format_relative_time(ts) == "now"

    def test_exactly_now(self) -> None:
        ts = datetime.now(UTC).isoformat()
        assert format_relative_time(ts) == "now"

    def test_minutes(self) -> None:
        ts = (datetime.now(UTC) - timedelta(minutes=17)).isoformat()
        assert format_relative_time(ts) == "17m"

    def test_one_minute(self) -> None:
        ts = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        assert format_relative_time(ts) == "1m"

    def test_fifty_nine_minutes(self) -> None:
        ts = (datetime.now(UTC) - timedelta(minutes=59)).isoformat()
        assert format_relative_time(ts) == "59m"

    def test_hours(self) -> None:
        ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert format_relative_time(ts) == "1h"

    def test_three_hours(self) -> None:
        ts = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
        assert format_relative_time(ts) == "3h"

    def test_days(self) -> None:
        ts = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        assert format_relative_time(ts) == "2d"

    def test_seven_days(self) -> None:
        ts = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        assert format_relative_time(ts) == "7d"

    def test_naive_timestamp_treated_as_utc(self) -> None:
        ts = (datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)).isoformat()
        assert format_relative_time(ts) == "5m"


class TestResolveGitBranch:
    def test_returns_branch_for_git_repo(self, tmp_path: Path) -> None:
        if shutil.which("git") is None:
            pytest.skip("git not available")
        _init_git_repo(tmp_path, "my-feature")

        assert resolve_git_branch(tmp_path) == "my-feature"

    def test_returns_none_for_non_git_dir(self, tmp_path: Path) -> None:
        assert resolve_git_branch(tmp_path) is None

    def test_returns_none_when_git_unavailable(self, tmp_path: Path) -> None:
        result = resolve_git_branch(tmp_path)
        if shutil.which("git") is None:
            assert result is None
        else:
            assert result is None

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        if shutil.which("git") is None:
            pytest.skip("git not available")
        _init_git_repo(tmp_path, "dev")

        assert resolve_git_branch(str(tmp_path)) == "dev"


class TestTomeListEntry:
    def test_fields(self) -> None:
        entry = TomeListEntry(
            tome_id="abc123",
            title="My Tome",
            created_at="2026-01-01T00:00:00+00:00",
            relative_time="2d",
            git_branch="main",
        )
        assert entry.tome_id == "abc123"
        assert entry.title == "My Tome"
        assert entry.git_branch == "main"
        assert entry.is_active is False

    def test_is_active_flag(self) -> None:
        entry = TomeListEntry(
            tome_id="abc123",
            title="My Tome",
            created_at="2026-01-01T00:00:00+00:00",
            relative_time="now",
            git_branch=None,
            is_active=True,
        )
        assert entry.is_active is True


class TestTomeServiceListTomes:
    def test_empty_tome_dir(self, tmp_path: Path) -> None:
        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(Path("/some/project"))
        assert entries == []

    def test_filters_by_project_cwd(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        ledger.create_tome("/project/a")
        ledger.create_tome("/project/b")
        ledger.create_tome("/project/a")

        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(Path("/project/a"))

        assert len(entries) == 2

    def test_entry_has_relative_time(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        ledger.create_tome("/project/a")

        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(Path("/project/a"))

        assert len(entries) == 1
        assert entries[0].relative_time == "now"

    def test_entry_has_git_branch(self, tmp_path: Path) -> None:
        if shutil.which("git") is None:
            pytest.skip("git not available")
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo, "feature-x")

        ledger = TomeLedger(tmp_path)
        ledger.create_tome(str(repo))

        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(repo)

        assert len(entries) == 1
        assert entries[0].git_branch == "feature-x"

    def test_active_flag_set(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        meta = ledger.create_tome("/project/a")

        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(
            Path("/project/a"), active_tome_id=meta.id
        )

        assert len(entries) == 1
        assert entries[0].is_active is True

    def test_active_flag_not_set_for_other(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        meta_a = ledger.create_tome("/project/a")
        ledger.create_tome("/project/a")

        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(
            Path("/project/a"), active_tome_id=meta_a.id
        )

        found = {e.tome_id: e for e in entries}
        assert found[meta_a.id].is_active is True
        for tome_id, entry in found.items():
            if tome_id != meta_a.id:
                assert entry.is_active is False

    def test_sorted_newest_first(self, tmp_path: Path) -> None:
        import json

        old_id = "a" * 32
        new_id = "b" * 32
        old_header = {
            "type": "session",
            "version": 3,
            "id": old_id,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "cwd": "/project/a",
            "schema_version": "1.0",
        }
        new_header = {
            "type": "session",
            "version": 3,
            "id": new_id,
            "timestamp": "2026-06-01T00:00:00+00:00",
            "cwd": "/project/a",
            "schema_version": "1.0",
        }
        (tmp_path / f"{old_id}.jsonl").write_text(
            json.dumps(old_header) + "\n", encoding="utf-8"
        )
        (tmp_path / f"{new_id}.jsonl").write_text(
            json.dumps(new_header) + "\n", encoding="utf-8"
        )

        service = TomeService(tmp_path)
        entries = service.list_tomes_for_project(Path("/project/a"))

        assert len(entries) == 2
        assert entries[0].tome_id == new_id
        assert entries[1].tome_id == old_id


class TestTomeServiceGetTitle:
    def test_title_from_tome_info_entry(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        meta = ledger.create_tome("/project/a")
        ledger.append_tome_info(meta.id, {"name": "My Custom Title"})

        service = TomeService(tmp_path)
        assert service.get_tome_title(meta.id) == "My Custom Title"

    def test_title_from_tome_info_title_key(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        meta = ledger.create_tome("/project/a")
        ledger.append_tome_info(meta.id, {"title": "Another Title"})

        service = TomeService(tmp_path)
        assert service.get_tome_title(meta.id) == "Another Title"

    def test_title_fallback_when_no_info(self, tmp_path: Path) -> None:
        ledger = TomeLedger(tmp_path)
        meta = ledger.create_tome("/project/a")

        service = TomeService(tmp_path)
        assert service.get_tome_title(meta.id) == "Conversation"

    def test_tome_dir_property(self, tmp_path: Path) -> None:
        service = TomeService(tmp_path)
        assert service.tome_dir == tmp_path
