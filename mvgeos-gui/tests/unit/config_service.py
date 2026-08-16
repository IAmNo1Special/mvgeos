"""Unit tests for mvgeos_gui.config_service."""

from __future__ import annotations

from pathlib import Path

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
        service.save_app_settings(AppSettings(api_key="sk-123", mana_limit=2048))

        loaded = service.load_app_settings()
        assert loaded.api_key == "sk-123"
        assert loaded.mana_limit == 2048

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
        service.save_app_settings(AppSettings(api_key="sk-123", mana_limit=2048))

        service.save_app_settings(AppSettings(temperature=0.9))
        loaded = service.load_app_settings()
        assert loaded.api_key == "sk-123"
        assert loaded.mana_limit == 2048
        assert loaded.temperature == 0.9
