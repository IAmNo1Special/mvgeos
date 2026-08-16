"""Settings persistence service for mvgeos-gui."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppSettings:
    """Global application settings."""

    api_key: str = ""
    default_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    mana_limit: int = 4096
    temperature: float = 0.7
    theme: str = "dark"


@dataclass
class WorkspaceSettings:
    """Per-project workspace settings."""

    project_name: str = ""
    spells_enabled: list[str] = field(
        default_factory=lambda: [
            "bash",
            "read",
            "write",
            "edit",
            "find",
            "list",
            "grep",
        ]
    )
    contemplation_level: str = "medium"


DEFAULT_APP_SETTINGS = AppSettings()
DEFAULT_WORKSPACE_SETTINGS = WorkspaceSettings()


class ConfigService:
    """Persist and load GUI settings from ~/.agents/.mvgeos/."""

    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or Path("~/.agents/.mvgeos").expanduser()
        self._config_dir = base.resolve()

    @property
    def app_settings_path(self) -> Path:
        return self._config_dir / "gui.json"

    def workspace_settings_path(self, project_dir: Path) -> Path:
        return (project_dir / ".agents" / ".mvgeos" / "workspace.json").resolve()

    def load_app_settings(self) -> AppSettings:
        if not self.app_settings_path.exists():
            return AppSettings()
        try:
            data = json.loads(self.app_settings_path.read_text(encoding="utf-8"))
            valid = {
                k: v for k, v in data.items() if k in AppSettings.__dataclass_fields__
            }
            return AppSettings(**valid)
        except json.JSONDecodeError, TypeError:
            return AppSettings()

    def save_app_settings(self, settings: AppSettings) -> None:
        self.app_settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if self.app_settings_path.exists():
            try:
                existing = json.loads(
                    self.app_settings_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError, OSError:
                existing = {}
        merged = {**existing, **self._settings_to_dict(settings)}
        self.app_settings_path.write_text(
            json.dumps(merged, indent=2), encoding="utf-8"
        )

    def _settings_to_dict(self, settings: AppSettings) -> dict[str, Any]:
        default = AppSettings()
        result: dict[str, Any] = {}
        if settings.api_key != default.api_key:
            result["api_key"] = settings.api_key
        if settings.default_model != default.default_model:
            result["default_model"] = settings.default_model
        if settings.mana_limit != default.mana_limit:
            result["mana_limit"] = settings.mana_limit
        if settings.temperature != default.temperature:
            result["temperature"] = settings.temperature
        if settings.theme != default.theme:
            result["theme"] = settings.theme
        return result

    def _workspace_settings_to_dict(
        self, settings: WorkspaceSettings
    ) -> dict[str, Any]:
        default = WorkspaceSettings()
        result: dict[str, Any] = {}
        if settings.project_name != default.project_name:
            result["project_name"] = settings.project_name
        if settings.spells_enabled != default.spells_enabled:
            result["spells_enabled"] = settings.spells_enabled
        if settings.contemplation_level != default.contemplation_level:
            result["contemplation_level"] = settings.contemplation_level
        return result

    def load_workspace_settings(self, project_dir: Path) -> WorkspaceSettings:
        path = self.workspace_settings_path(project_dir)
        if not path.exists():
            return WorkspaceSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid_keys = {
                k: v
                for k, v in data.items()
                if k in WorkspaceSettings.__dataclass_fields__
            }
            return WorkspaceSettings(**valid_keys)
        except json.JSONDecodeError, TypeError:
            return WorkspaceSettings()

    def save_workspace_settings(
        self, project_dir: Path, settings: WorkspaceSettings
    ) -> None:
        path = self.workspace_settings_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError, OSError:
                existing = {}
        merged = {**existing, **self._workspace_settings_to_dict(settings)}
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
