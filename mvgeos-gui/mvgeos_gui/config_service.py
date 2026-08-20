"""Settings persistence service for mvgeos-gui."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_KEYRING_SERVICE = "mvgeos"
_KEYRING_API_KEY_USERNAME = "openrouter_api_key"
_API_KEY_FIELD = "api_key"


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


def _load_api_key_from_keyring() -> str | None:
    """Load the OpenRouter API key from the OS keyring.

    Returns None if the keyring is unavailable or the key is not stored.
    """
    with contextlib.suppress(Exception):
        import keyring

        key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_API_KEY_USERNAME)
        if key:
            return key
    return None


def _save_api_key_to_keyring(api_key: str) -> None:
    """Persist the OpenRouter API key to the OS keyring.

    Silently ignored if the keyring backend is unavailable.
    """
    if not api_key:
        return
    with contextlib.suppress(Exception):
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_API_KEY_USERNAME, api_key)


def _delete_api_key_from_keyring() -> None:
    """Remove the OpenRouter API key from the OS keyring.

    Silently ignored if the keyring backend is unavailable or the key
    is not present.
    """
    with contextlib.suppress(Exception):
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_API_KEY_USERNAME)


def _set_config_file_permissions(path: Path) -> None:
    """Restrict config file permissions to owner read/write only.

    On POSIX systems this sets mode 0o600. On Windows it uses icacls
    to remove access for everyone except the current user.
    """
    if not path.exists():
        return
    try:
        if os.name == "posix":
            os.chmod(path, 0o600)
        elif os.name == "nt":
            import subprocess

            with contextlib.suppress(Exception):
                subprocess.run(
                    [
                        "icacls",
                        str(path),
                        "/inheritance:r",
                        "/grant:r",
                        f"{os.environ.get('USERNAME', 'USER')}:(F)",
                    ],
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
    except Exception:
        pass


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
            settings = AppSettings(**valid)
        except json.JSONDecodeError, TypeError:
            return AppSettings()

        # Backfill from keyring if the file has no api_key but the keyring
        # does.  This handles users who previously saved a key and now have
        # it in the OS credential store.
        if not settings.api_key:
            keyring_key = _load_api_key_from_keyring()
            if keyring_key:
                settings.api_key = keyring_key

        return settings

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

        # The API key is stored in the OS keyring, not in the JSON file.
        # Remove it from the file payload if present.
        merged.pop(_API_KEY_FIELD, None)

        # Persist the API key to the OS keyring.
        if settings.api_key:
            _save_api_key_to_keyring(settings.api_key)
        else:
            _delete_api_key_from_keyring()

        self.app_settings_path.write_text(
            json.dumps(merged, indent=2), encoding="utf-8"
        )
        _set_config_file_permissions(self.app_settings_path)

    def _settings_to_dict(self, settings: AppSettings) -> dict[str, Any]:
        default = AppSettings()
        result: dict[str, Any] = {}
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
