from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mvgeos_cli.commands.config import (
    DEFAULT_CONFIG,
    config_app,
    load_config,
    save_config,
)

runner = CliRunner()


class TestConfigCommands:
    def test_config_app_exists(self) -> None:
        assert config_app is not None

    def test_default_config_contains_expected_keys(self) -> None:
        assert "model" in DEFAULT_CONFIG
        assert "max_tokens" in DEFAULT_CONFIG
        assert "spells_enabled" in DEFAULT_CONFIG

    def test_load_config_no_file(self) -> None:
        with patch(
            "mvgeos_cli.commands.config.CONFIG_FILE",
            Path("/nonexistent/config.json"),
        ):
            config = load_config()
            assert config == DEFAULT_CONFIG.copy()

    def test_load_config_with_file(self) -> None:
        test_config = {"model": "test-model", "max_tokens": 5000}
        cfg_path = Path("/tmp/test_config.json")
        with (
            patch("mvgeos_cli.commands.config.CONFIG_FILE", cfg_path),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=json.dumps(test_config)),
        ):
            config = load_config()
            assert config == test_config

    def test_save_config(self) -> None:
        config = {"model": "test", "max_tokens": 100}
        with (
            patch("mvgeos_cli.commands.config.CONFIG_DIR", Path("/tmp")),
            patch("mvgeos_cli.commands.config.CONFIG_FILE", Path("/tmp/config.json")),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.write_text") as mock_write,
        ):
            save_config(config)
            mock_write.assert_called_once_with(
                json.dumps(config, indent=2), encoding="utf-8"
            )

    @patch("mvgeos_cli.commands.config.load_config")
    def test_config_show(self, mock_load: MagicMock) -> None:
        runner = CliRunner()
        mock_load.return_value = {"model": "test-model", "max_tokens": 5000}

        result = runner.invoke(config_app, ["show"])
        assert result.exit_code == 0
        assert "test-model" in result.stdout

    def test_config_set(self) -> None:
        with (
            patch(
                "mvgeos_cli.commands.config.load_config",
                return_value={"model": "test"},
            ),
            patch("mvgeos_cli.commands.config.save_config") as mock_save,
        ):
            result = runner.invoke(config_app, ["set", "model", "new-model"])
            assert result.exit_code == 0
            assert "Set model = new-model" in result.stdout
            mock_save.assert_called_once()

    def test_config_set_json_value(self) -> None:
        with (
            patch("mvgeos_cli.commands.config.load_config", return_value={}),
            patch("mvgeos_cli.commands.config.save_config") as mock_save,
        ):
            result = runner.invoke(config_app, ["set", "list_val", "[1, 2, 3]"])
            assert result.exit_code == 0
            saved_config = mock_save.call_args[0][0]
            assert saved_config["list_val"] == [1, 2, 3]

    def test_config_get(self) -> None:
        with patch(
            "mvgeos_cli.commands.config.load_config",
            return_value={"model": "test-model"},
        ):
            result = runner.invoke(config_app, ["get", "model"])
            assert result.exit_code == 0
            assert "test-model" in result.stdout

    def test_config_get_not_found(self) -> None:
        with patch("mvgeos_cli.commands.config.load_config", return_value={}):
            result = runner.invoke(config_app, ["get", "nonexistent"])
            assert result.exit_code == 1
            assert "Key not found" in result.stdout

    def test_config_reset(self) -> None:
        with patch("mvgeos_cli.commands.config.save_config") as mock_save:
            result = runner.invoke(config_app, ["reset"])
            assert result.exit_code == 0
            assert "Configuration reset to defaults" in result.stdout
            mock_save.assert_called_once_with(DEFAULT_CONFIG.copy())

    def test_config_path(self) -> None:
        test_path = Path("/test/.agents/.mvgeos/config.json")
        with patch("mvgeos_cli.commands.config.CONFIG_FILE", test_path):
            result = runner.invoke(config_app, ["path"])
            assert result.exit_code == 0
            resolved = str(test_path.resolve())
            assert str(test_path) in result.stdout or resolved in result.stdout
