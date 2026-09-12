from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mvgeos_cli.commands.mvge import mvge_app
from mvgeos_cli.main import app

runner = CliRunner()


def test_mvge_install_success(tmp_path: Path) -> None:
    dest_path = tmp_path / "coding_mvge"
    with patch(
        "mvgeos_cli.commands.mvge.install_mvge", return_value=dest_path
    ) as mock_install:
        result = runner.invoke(mvge_app, ["install", "coding_mvge"])
        assert result.exit_code == 0
        assert "Successfully installed mvge 'coding_mvge'" in result.stdout
        mock_install.assert_called_once_with("coding_mvge")


def test_mvge_install_error() -> None:
    with patch(
        "mvgeos_cli.commands.mvge.install_mvge", side_effect=ValueError("Not found")
    ):
        result = runner.invoke(mvge_app, ["install", "unknown_mvge"])
        assert result.exit_code != 0
        assert "Not found" in result.stdout


def test_mvge_list_empty() -> None:
    with patch("mvgeos_cli.commands.mvge.list_installed_mvges", return_value=[]):
        result = runner.invoke(mvge_app, ["list"])
        assert result.exit_code == 0
        assert "No agent mvges installed" in result.stdout


def test_mvge_list_with_items() -> None:
    mock_items = [
        {
            "name": "coding_mvge",
            "version": "0.2.6",
            "description": "Coding agent",
            "spells": ["bash", "read", "write"],
        }
    ]
    with patch(
        "mvgeos_cli.commands.mvge.list_installed_mvges", return_value=mock_items
    ):
        result = runner.invoke(mvge_app, ["list"])
        assert result.exit_code == 0
        assert "coding_mvge" in result.stdout
        assert "0.2.6" in result.stdout
        assert "bash, read, write" in result.stdout


def test_mvge_uninstall_success() -> None:
    with patch("mvgeos_cli.commands.mvge.uninstall_mvge", return_value=True):
        result = runner.invoke(mvge_app, ["uninstall", "coding_mvge"])
        assert result.exit_code == 0
        assert "Successfully uninstalled mvge 'coding_mvge'" in result.stdout


def test_mvge_uninstall_not_found() -> None:
    with patch("mvgeos_cli.commands.mvge.uninstall_mvge", return_value=False):
        result = runner.invoke(mvge_app, ["uninstall", "nonexistent"])
        assert result.exit_code == 0
        assert "Mvge 'nonexistent' is not installed" in result.stdout


def test_agent_alias_subcommand(tmp_path: Path) -> None:
    dest_path = tmp_path / "coding_mvge"
    with patch("mvgeos_cli.commands.mvge.install_mvge", return_value=dest_path):
        result = runner.invoke(app, ["agent", "install", "coding_mvge"])
        assert result.exit_code == 0
        assert "Successfully installed mvge 'coding_mvge'" in result.stdout


def test_mvge_list_exception() -> None:
    with patch(
        "mvgeos_cli.commands.mvge.list_installed_mvges",
        side_effect=RuntimeError("db error"),
    ):
        result = runner.invoke(mvge_app, ["list"])
        assert result.exit_code != 0
        assert "db error" in result.stdout


def test_mvge_uninstall_exception() -> None:
    with patch(
        "mvgeos_cli.commands.mvge.uninstall_mvge", side_effect=RuntimeError("io error")
    ):
        result = runner.invoke(mvge_app, ["uninstall", "failing"])
        assert result.exit_code != 0
        assert "io error" in result.stdout
