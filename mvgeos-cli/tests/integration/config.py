from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mvgeos_cli.commands.config import config_app

runner = CliRunner()


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
            config_app, ["set", "list_val", "[1, 2, 3]", "--agent-name", "test-agent"]
        )
        assert result.exit_code == 0
        mock_mgr.set.assert_called_once_with("list_val", [1, 2, 3])

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
