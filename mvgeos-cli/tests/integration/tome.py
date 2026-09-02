from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeMetadata
from typer.testing import CliRunner

from mvgeos_cli.commands.tome import (
    _render_tome_list,
    get_tome_dir,
    tome_app,
)
from mvgeos_cli.main import app


def _make_meta(tome_id: str, cwd: str) -> TomeMetadata:
    return TomeMetadata(
        id=tome_id,
        created_at="2024-01-01T12:00:00",
        cwd=cwd,
        parent_tome_id=None,
        active_leaf_id=None,
        schema_version="1.0",
    )


runner = CliRunner()


def test_tome_no_subcommand_prints_help() -> None:
    result = runner.invoke(app, ["tome"])
    assert result.exit_code == 0
    assert "Session tome management" in result.stdout
    assert "Commands" in result.stdout
    assert "Missing command" not in result.output


class TestTomeCommands:
    def test_tome_app_exists(self) -> None:
        assert tome_app is not None
        assert isinstance(tome_app, typer.Typer)

    def test_get_tome_dir(self) -> None:
        result = get_tome_dir()
        assert result == Path.home() / ".agents" / ".mvgeos" / "tomes"

    def test_tome_list_help(self) -> None:
        result = runner.invoke(tome_app, ["list", "--help"])
        assert result.exit_code == 0
        assert "List all tomes" in result.stdout

    def test_tome_show_help(self) -> None:
        result = runner.invoke(tome_app, ["show", "--help"])
        assert result.exit_code == 0
        assert "Show tome details" in result.stdout

    def test_tome_export_help(self) -> None:
        result = runner.invoke(tome_app, ["export", "--help"])
        assert result.exit_code == 0
        assert "Export a tome" in result.stdout

    def test_tome_create_help(self) -> None:
        result = runner.invoke(tome_app, ["create", "--help"])
        assert result.exit_code == 0
        assert "Create a new tome" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_list_empty(self, mock_ledger: MagicMock, mock_cwd: MagicMock) -> None:
        mock_ledger_instance = MagicMock()
        mock_ledger_instance._tomes = {}
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["list"])
        assert result.exit_code == 0

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_list_with_sessions(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.active_leaf_id = "leaf_123"

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.list_tomes.return_value = [mock_meta]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["list"])
        assert result.exit_code == 0
        assert "tome_abc" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_show_not_found(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = None
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "Tome not found" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_show_found(self, mock_ledger: MagicMock, mock_cwd: MagicMock) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.active_leaf_id = "leaf_123"

        mock_entry = MagicMock()
        mock_entry.type.value = "message"
        mock_entry.timestamp = 1786553222.331
        mock_entry.payload = {"key": "value"}

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["show", "tome_abc123"])
        assert result.exit_code == 0
        assert "tome_abc" in result.stdout
        assert "2026-08-12T16:47:02.331000+00:00" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_show_format_markdown_matches_export(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.parent_tome_id = None
        mock_meta.active_leaf_id = "leaf_123"
        mock_meta.schema_version = "1.0"

        mock_entry = MagicMock()
        mock_entry.type.value = "message"
        mock_entry.timestamp = 1786553222.331
        mock_entry.payload = {"key": "value"}

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        show_res = runner.invoke(
            tome_app, ["show", "tome_abc123", "--format", "markdown"]
        )
        export_res = runner.invoke(
            tome_app, ["export", "tome_abc123", "--format", "markdown"]
        )
        assert show_res.exit_code == 0
        assert export_res.exit_code == 0
        assert show_res.stdout == export_res.stdout
        assert "2026-08-12T16:47:02.331000+00:00" in show_res.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_show_format_json_matches_export(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.parent_tome_id = None
        mock_meta.active_leaf_id = "leaf_123"
        mock_meta.schema_version = "1.0"

        mock_entry = MagicMock()
        mock_entry.id = "entry_123"
        mock_entry.parent_id = None
        mock_entry.type.value = "message"
        mock_entry.timestamp = 1786553222.331
        mock_entry.payload = {"key": "value"}

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        show_res = runner.invoke(tome_app, ["show", "tome_abc123", "--format", "json"])
        export_res = runner.invoke(
            tome_app, ["export", "tome_abc123", "--format", "json"]
        )
        assert show_res.exit_code == 0
        assert export_res.exit_code == 0
        assert show_res.stdout == export_res.stdout
        assert "2026-08-12T16:47:02.331000+00:00" in show_res.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_show_invalid_format_exits_with_error(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger.return_value = mock_ledger_instance

        result = runner.invoke(tome_app, ["show", "tome_abc123", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Unknown format" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_export_json(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.parent_tome_id = None
        mock_meta.active_leaf_id = "leaf_123"
        mock_meta.schema_version = "1.0"

        mock_entry = MagicMock()
        mock_entry.id = "entry_123"
        mock_entry.parent_id = None
        mock_entry.type.value = "message"
        mock_entry.timestamp = 123.456
        mock_entry.payload = {"key": "value"}

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["export", "tome_abc123", "--format", "json"])
        assert result.exit_code == 0
        assert "tome_abc123" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_export_markdown(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.parent_tome_id = None
        mock_meta.active_leaf_id = "leaf_123"
        mock_meta.schema_version = "1.0"

        mock_entry = MagicMock()
        mock_entry.type.value = "message"
        mock_entry.timestamp = 123.456
        mock_entry.payload = {"key": "value"}

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(
            tome_app,
            ["export", "tome_abc123", "--format", "markdown"],
        )
        assert result.exit_code == 0
        assert "tome_abc" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_export_tool_result_json(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        import json

        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.parent_tome_id = None
        mock_meta.active_leaf_id = "leaf_123"
        mock_meta.schema_version = "1.0"

        mock_entry = MagicMock()
        mock_entry.id = "entry_tool_1"
        mock_entry.parent_id = "entry_prev"
        mock_entry.type.value = "message"
        mock_entry.timestamp = 1786553222.331
        mock_entry.payload = {
            "role": "tool",
            "content": [{"type": "text", "text": "file content here"}],
            "model": None,
            "provider": None,
        }

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["export", "tome_abc123", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["metadata"]["id"] == "tome_abc123"
        assert len(parsed["entries"]) == 1
        assert parsed["entries"][0]["payload"]["role"] == "tool"
        assert parsed["entries"][0]["payload"]["content"] == [
            {"type": "text", "text": "file content here"}
        ]

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_export_tool_result_markdown(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.parent_tome_id = None
        mock_meta.active_leaf_id = "leaf_123"
        mock_meta.schema_version = "1.0"

        mock_entry = MagicMock()
        mock_entry.id = "entry_tool_1"
        mock_entry.parent_id = "entry_prev"
        mock_entry.type.value = "message"
        mock_entry.timestamp = 1786553222.331
        mock_entry.payload = {
            "role": "tool",
            "content": [{"type": "text", "text": "file content here"}],
            "model": None,
            "provider": None,
        }

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(
            tome_app, ["export", "tome_abc123", "--format", "markdown"]
        )
        assert result.exit_code == 0
        assert "# Tome: tome_abc" in result.stdout
        assert "## message" in result.stdout
        assert '"role": "tool"' in result.stdout
        assert '"text": "file content here"' in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_export_not_found(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = None
        mock_ledger.return_value = mock_ledger_instance

        result = runner.invoke(tome_app, ["export", "nonexistent"])
        assert result.exit_code == 1
        assert "Tome not found" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_create(self, mock_ledger: MagicMock, mock_cwd: MagicMock) -> None:
        mock_cwd.return_value = Path("/test")
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.create_tome.return_value = mock_meta
        mock_ledger.return_value = mock_ledger_instance

        result = runner.invoke(tome_app, ["create"])
        assert result.exit_code == 0
        assert "Created tome: tome_abc" in result.stdout

    @patch("mvgeos_cli.commands.tome.Path.cwd")
    @patch("mvgeos_cli.commands.tome.TomeLedger")
    def test_tome_fork_short_id(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "parent_tome_123456"
        mock_meta.cwd = "/test"

        forked_meta = MagicMock()
        forked_meta.id = "forked_tome_654321"

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_leaf_id.return_value = "leaf_001"
        mock_ledger_instance.get_entry.return_value = MagicMock()
        mock_ledger_instance.create_branched_tome.return_value = forked_meta
        mock_ledger.return_value = mock_ledger_instance

        result = runner.invoke(tome_app, ["fork", "parent_t"])
        assert result.exit_code == 0
        assert "Forked tome: forked_t" in result.stdout
        assert "Parent: parent_t" in result.stdout

    def test_tome_fork_with_leaf_ancestors(self, tmp_path: Path) -> None:
        import tempfile

        from mvgeos_tome.ledger import TomeLedger

        with tempfile.TemporaryDirectory() as tmp_tome_dir:
            tome_dir = Path(tmp_tome_dir)
            ledger = TomeLedger(tome_dir)
            meta = ledger.create_tome("/tmp")

            e1 = ledger.append_message(meta.id, "user", "turn 1 req", parent_id=None)
            ledger.append_leaf(meta.id, e1.id)

            e2 = ledger.append_message(
                meta.id, "assistant", "turn 1 resp", parent_id=e1.id
            )
            ledger.append_leaf(meta.id, e2.id)

            e3 = ledger.append_message(meta.id, "user", "turn 2 req", parent_id=e2.id)
            ledger.append_leaf(meta.id, e3.id)

            with patch("mvgeos_cli.commands.tome.get_tome_dir", return_value=tome_dir):
                result = runner.invoke(tome_app, ["fork", meta.id, "--leaf", e2.id])
                assert result.exit_code == 0
                assert "Forked tome:" in result.stdout

                # Verify on disk
                fresh_ledger = TomeLedger(tome_dir)
                tomes = fresh_ledger.list_tomes()
                forked_meta = next(t for t in tomes if t.id != meta.id)
                assert forked_meta.parent_tome_id == meta.id
                assert forked_meta.active_leaf_id == e2.id

                entries = fresh_ledger.get_entries(forked_meta.id)
                assert len(entries) == 2
                assert entries[0].id == e1.id
                assert entries[0].parent_id is None
                assert entries[1].id == e2.id
                assert entries[1].parent_id == e1.id


def test_render_tome_list_ellipsizes_long_cwd() -> None:
    long_cwd = "/a" + "/b" * 90
    meta = _make_meta("tome_abc123", long_cwd)
    output = _render_tome_list([meta], ascii_only=False)
    assert "…" in output
    assert long_cwd not in output


def test_render_tome_list_short_cwd_kept_full() -> None:
    meta = _make_meta("tome_abc123", "/short/cwd")
    output = _render_tome_list([meta], ascii_only=False)
    assert "/short/cwd" in output
    assert "…" not in output


def test_render_tome_list_ascii_long_cwd_uses_ascii_ellipsis() -> None:
    long_cwd = "/a" + "/b" * 90
    meta = _make_meta("tome_abc123", long_cwd)
    output = _render_tome_list([meta], ascii_only=True)
    assert "..." in output
    assert "…" not in output
    assert all(ord(ch) < 128 for ch in output)


def test_tome_verify_help() -> None:
    result = runner.invoke(tome_app, ["verify", "--help"])
    assert result.exit_code == 0
    assert "Verify integrity of a tome session file" in result.stdout


def test_tome_verify_valid_session(tmp_path: Path) -> None:
    ledger = TomeLedger(tmp_path)
    meta = ledger.create_tome("/workspace")
    ledger.append_message(meta.id, "user", "hi")

    with patch("mvgeos_cli.commands.tome.get_tome_dir", return_value=tmp_path):
        result = runner.invoke(tome_app, ["verify", meta.id])
        assert result.exit_code == 0
        assert "is valid" in result.stdout


def test_tome_verify_corrupted_session(tmp_path: Path) -> None:
    ledger = TomeLedger(tmp_path)
    meta = ledger.create_tome("/workspace")
    tome_file = ledger.tome_file(meta.id)
    with tome_file.open("a", encoding="utf-8") as f:
        f.write('{"id": "bad", "truncated": true\n')

    with patch("mvgeos_cli.commands.tome.get_tome_dir", return_value=tmp_path):
        result = runner.invoke(tome_app, ["verify", meta.id])
        assert result.exit_code == 1
        assert "integrity issue" in result.stdout
        assert "Line 2:" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
