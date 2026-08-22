"""Unit tests for mvgeos_gui.config_service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mvgeos_gui.config_service import (
    AppSettings,
    ConfigService,
    WorkspaceSettings,
)


class TestAppSettings:
    def test_defaults(self) -> None:
        settings = AppSettings()
        assert settings.api_key == ""
        assert settings.default_model == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert settings.mana_limit == 4096
        assert settings.temperature == 0.7
        assert settings.theme == "dark"

    def test_custom_init(self) -> None:
        settings = AppSettings(
            api_key="sk-test",
            default_model="anthropic/claude-3.5-sonnet",
            mana_limit=8192,
            temperature=0.5,
            theme="light",
        )
        assert settings.api_key == "sk-test"
        assert settings.default_model == "anthropic/claude-3.5-sonnet"
        assert settings.mana_limit == 8192
        assert settings.temperature == 0.5
        assert settings.theme == "light"


class TestWorkspaceSettings:
    def test_defaults(self) -> None:
        settings = WorkspaceSettings()
        assert settings.project_name == ""
        assert settings.spells_enabled == [
            "bash",
            "read",
            "write",
            "edit",
            "find",
            "list",
            "grep",
        ]
        assert settings.contemplation_level == "medium"

    def test_custom_init(self) -> None:
        settings = WorkspaceSettings(
            project_name="my-project",
            spells_enabled=["bash", "read"],
            contemplation_level="high",
        )
        assert settings.project_name == "my-project"
        assert settings.spells_enabled == ["bash", "read"]
        assert settings.contemplation_level == "high"


class TestConfigService:
    def test_load_global_defaults_when_no_file(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        settings = service.load_app_settings()
        assert settings.api_key == ""
        assert settings.default_model == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert settings.mana_limit == 4096

    def test_save_and_load_app_settings(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        with patch(
            "mvgeos_gui.config_service._save_api_key_to_keyring",
            return_value=True,
        ) as mock_save:
            service.save_app_settings(AppSettings(api_key="sk-123", mana_limit=2048))

        with patch(
            "mvgeos_gui.config_service._load_api_key_from_keyring",
            return_value="sk-123",
        ):
            loaded = service.load_app_settings()

        assert loaded.api_key == "sk-123"
        assert loaded.mana_limit == 2048
        mock_save.assert_called_once_with("sk-123")

    def test_save_and_load_workspace_settings(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        service.save_workspace_settings(
            project_dir, WorkspaceSettings(project_name="test-proj")
        )

        loaded = service.load_workspace_settings(project_dir)
        assert loaded.project_name == "test-proj"

    def test_workspace_settings_defaults_when_no_file(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        loaded = service.load_workspace_settings(project_dir)
        assert loaded.project_name == ""
        assert loaded.contemplation_level == "medium"

    def test_global_settings_path(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        expected = tmp_path / "gui.json"
        assert service.app_settings_path == expected

    def test_workspace_settings_path(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        expected = project_dir / ".agents" / ".mvgeos" / "workspace.json"
        assert service.workspace_settings_path(project_dir) == expected

    def test_partial_update_preserves_other_keys(self, tmp_path: Path) -> None:
        service = ConfigService(config_dir=tmp_path)
        with patch(
            "mvgeos_gui.config_service._save_api_key_to_keyring",
            return_value=True,
        ):
            service.save_app_settings(AppSettings(api_key="sk-123", mana_limit=2048))

        with patch(
            "mvgeos_gui.config_service._load_api_key_from_keyring",
            return_value="sk-123",
        ):
            service.save_app_settings(AppSettings(temperature=0.9))
            loaded = service.load_app_settings()

        assert loaded.api_key == "sk-123"
        assert loaded.mana_limit == 2048
        assert loaded.temperature == 0.9

    def test_api_key_not_written_to_file(self, tmp_path: Path) -> None:
        """Verify the API key is never persisted to the JSON file."""
        service = ConfigService(config_dir=tmp_path)
        with patch(
            "mvgeos_gui.config_service._save_api_key_to_keyring",
            return_value=True,
        ):
            service.save_app_settings(AppSettings(api_key="secret-key"))

        data = json.loads((tmp_path / "gui.json").read_text(encoding="utf-8"))
        assert "api_key" not in data

    def test_api_key_falls_back_to_file_when_keyring_unavailable(
        self, tmp_path: Path
    ) -> None:
        """Without a usable keyring backend the key must persist to the
        owner-only config file instead of being silently lost."""
        service = ConfigService(config_dir=tmp_path)
        with patch(
            "mvgeos_gui.config_service._save_api_key_to_keyring",
            return_value=False,
        ):
            service.save_app_settings(AppSettings(api_key="sk-fallback"))

        data = json.loads((tmp_path / "gui.json").read_text(encoding="utf-8"))
        assert data["api_key"] == "sk-fallback"

        loaded = service.load_app_settings()
        assert loaded.api_key == "sk-fallback"

    def test_backfill_api_key_from_keyring(self, tmp_path: Path) -> None:
        """Verify API key is loaded from keyring when missing from file."""
        service = ConfigService(config_dir=tmp_path)

        # Save settings without keyring having the key
        with patch(
            "mvgeos_gui.config_service._save_api_key_to_keyring",
            return_value=True,
        ):
            service.save_app_settings(AppSettings(mana_limit=2048))

        # Now simulate keyring having the key
        with patch(
            "mvgeos_gui.config_service._load_api_key_from_keyring",
            return_value="keyring-key",
        ):
            loaded = service.load_app_settings()

        assert loaded.api_key == "keyring-key"
        assert loaded.mana_limit == 2048
