from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
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
        mock_ledger_instance._tomles = {}
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
        mock_entry.type.value = "invocation"
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
        mock_entry.type.value = "invocation"
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
        mock_entry.type.value = "invocation"
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
        mock_entry.type.value = "invocation"
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
        mock_entry.type.value = "invocation"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
