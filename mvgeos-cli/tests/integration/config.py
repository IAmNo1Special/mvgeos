from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mvgeos_cli.commands.config import config_app
from mvgeos_cli.main import app

runner = CliRunner()


def test_config_no_subcommand_prints_help() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "Configuration management" in result.stdout
    assert "Commands" in result.stdout
    assert "Missing command" not in result.output


class TestConfigCommands:
    def test_config_app_exists(self) -> None:
        assert config_app is not None

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_show(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = {
            "model": MagicMock(value="test-model", layer=MagicMock(value="agent")),
        }
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["show", "--agent-name", "test-agent"])
        assert result.exit_code == 0
        assert "test-model" in result.stdout
        mock_manager_cls.assert_called_once_with(agent_name="test-agent")

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_show_default_agent(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = {}
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["show"])
        assert result.exit_code == 0
        mock_manager_cls.assert_called_once_with(agent_name="default-mvge")

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_set(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app, ["set", "model", "new-model", "--agent-name", "test-agent"]
        )
        assert result.exit_code == 0
        assert "Set model = new-model" in result.stdout
        mock_mgr.set.assert_called_once_with("model", "new-model")

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_set_json_value(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app,
            ["set", "spells_enabled", '["bash", "read"]', "--agent-name", "test-agent"],
        )
        assert result.exit_code == 0
        mock_mgr.set.assert_called_once_with("spells_enabled", ["bash", "read"])

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_set_invalid_temperature(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_mgr.set.side_effect = ValueError(
            "Invalid temperature value: expected float"
        )
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app, ["set", "temperature", "invalid", "--agent-name", "test-agent"]
        )
        assert result.exit_code == 1
        assert "Invalid temperature value: expected float" in result.output

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_get(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_val = MagicMock()
        mock_val.value = "test-model"
        mock_val.layer = MagicMock(value="agent")
        mock_mgr.get.return_value = mock_val
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(
            config_app, ["get", "model", "--agent-name", "test-agent"]
        )
        assert result.exit_code == 0
        assert "test-model" in result.stdout

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_reset(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["reset", "--agent-name", "test-agent"])
        assert result.exit_code == 0
        assert "Configuration reset to defaults" in result.stdout
        mock_mgr.reset.assert_called_once()

    @patch("mvgeos_cli.commands.config.ConfigManager")
    def test_config_path(self, mock_manager_cls: MagicMock) -> None:
        runner = CliRunner()
        mock_mgr = MagicMock()
        mock_mgr.agent_config_path = Path(
            "/home/user/.agents/.mvgeos/test-agent/config.json"
        )
        mock_manager_cls.return_value = mock_mgr

        result = runner.invoke(config_app, ["path", "--agent-name", "test-agent"])
        assert result.exit_code == 0
        assert "test-agent" in result.stdout
        assert "config.json" in result.stdout
