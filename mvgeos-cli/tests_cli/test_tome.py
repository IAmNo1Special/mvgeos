from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from mvgeos.commands.tome import (
    tome_app,
)

runner = CliRunner()


class TestTomeCommands:
    def test_tome_app_exists(self) -> None:
        assert tome_app is not None
        assert isinstance(tome_app, typer.Typer)

    def test_tome_list_help(self) -> None:
        result = runner.invoke(tome_app, ["list", "--help"])
        assert result.exit_code == 0
        assert "List all sessions" in result.stdout

    def test_tome_show_help(self) -> None:
        result = runner.invoke(tome_app, ["show", "--help"])
        assert result.exit_code == 0
        assert "Show session details" in result.stdout

    def test_tome_export_help(self) -> None:
        result = runner.invoke(tome_app, ["export", "--help"])
        assert result.exit_code == 0
        assert "Export a session" in result.stdout

    def test_tome_create_help(self) -> None:
        result = runner.invoke(tome_app, ["create", "--help"])
        assert result.exit_code == 0
        assert "Create a new session" in result.stdout

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
    def test_tome_list_empty(self, mock_ledger: MagicMock, mock_cwd: MagicMock) -> None:
        mock_ledger_instance = MagicMock()
        mock_ledger_instance._tomles = {}
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["list"])
        assert result.exit_code == 0

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
    def test_tome_list_with_sessions(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.active_leaf_id = "leaf_123"

        mock_ledger_instance = MagicMock()
        mock_ledger_instance._tomles = {"tome_abc123": mock_meta}
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["list"])
        assert result.exit_code == 0
        assert "tome_abc123" in result.stdout

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
    def test_tome_show_not_found(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = None
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.stdout

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
    def test_tome_show_found(self, mock_ledger: MagicMock, mock_cwd: MagicMock) -> None:
        mock_meta = MagicMock()
        mock_meta.id = "tome_abc123"
        mock_meta.created_at = "2024-01-01T12:00:00"
        mock_meta.cwd = "/test"
        mock_meta.active_leaf_id = "leaf_123"

        mock_entry = MagicMock()
        mock_entry.type.value = "invocation"
        mock_entry.timestamp = 123.456
        mock_entry.payload = {"key": "value"}

        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = mock_meta
        mock_ledger_instance.get_entries.return_value = [mock_entry]
        mock_ledger.return_value = mock_ledger_instance
        mock_cwd.return_value = Path("/test")

        result = runner.invoke(tome_app, ["show", "tome_abc123"])
        assert result.exit_code == 0
        assert "tome_abc123" in result.stdout

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
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

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
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
        assert "Session: tome_abc123" in result.stdout

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
    def test_tome_export_not_found(
        self, mock_ledger: MagicMock, mock_cwd: MagicMock
    ) -> None:
        mock_ledger_instance = MagicMock()
        mock_ledger_instance.open_tome.return_value = None
        mock_ledger.return_value = mock_ledger_instance

        result = runner.invoke(tome_app, ["export", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.stdout

    @patch("mvgeos.commands.tome.Path.cwd")
    @patch("mvgeos.commands.tome.TomeLedger")
    def test_tome_create(self, mock_ledger: MagicMock, mock_cwd: MagicMock) -> None:
        mock_cwd.return_value = Path("/test")

        mock_ledger_instance = MagicMock()
        mock_ledger.return_value = mock_ledger_instance

        result = runner.invoke(tome_app, ["create"])
        assert result.exit_code == 0
        assert "Created session" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
