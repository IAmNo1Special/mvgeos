"""Settings persistence service for mvgeos-gui."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import keyring
from mvgeos_agent.config_manager import ConfigManager

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
    temperature: float = 0.7
    max_tokens: int = 4096
    model: str = ""


def _load_api_key_from_keyring() -> str | None:
    """Load the OpenRouter API key from the OS keyring.

    Returns None if the keyring is unavailable or the key is not stored.
    """
    with contextlib.suppress(Exception):
        key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_API_KEY_USERNAME)
        if key:
            return key
    return None


def _save_api_key_to_keyring(api_key: str) -> bool:
    """Persist the OpenRouter API key to the OS keyring.

    Returns True on success, False if no usable keyring backend exists.
    """
    if not api_key:
        return True
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_API_KEY_USERNAME, api_key)
    except Exception:
        return False
    return True


def _delete_api_key_from_keyring() -> None:
    """Remove the OpenRouter API key from the OS keyring.

    Silently ignored if the keyring backend is unavailable or the key
    is not present.
    """
    with contextlib.suppress(Exception):
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
        return (project_dir / ".agents" / ".mvgeos" / "config.json").resolve()

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

        # The API key lives in the OS keyring when one is available; it
        # never touches disk unless the backend is missing.
        merged.pop(_API_KEY_FIELD, None)

        if settings.api_key:
            stored_in_keyring = _save_api_key_to_keyring(settings.api_key)
        else:
            _delete_api_key_from_keyring()
            stored_in_keyring = True

        if not stored_in_keyring:
            # No usable keyring backend: fall back to the owner-only
            # config file rather than silently losing the key.
            merged[_API_KEY_FIELD] = settings.api_key

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

    def load_workspace_settings(self, project_dir: Path) -> WorkspaceSettings:
        cm = ConfigManager(project_dir=project_dir)
        config_values = cm.load()

        spells_val = config_values.get("spells_enabled")
        spells_enabled = (
            list(spells_val.value)
            if spells_val is not None and isinstance(spells_val.value, list)
            else [
                "bash",
                "read",
                "write",
                "edit",
                "find",
                "list",
                "grep",
            ]
        )

        contemplation_val = config_values.get("contemplation_level")
        contemplation_level = (
            str(contemplation_val.value) if contemplation_val is not None else "medium"
        )

        temp_val = config_values.get("temperature")
        temperature = float(temp_val.value) if temp_val is not None else 0.7

        tokens_val = config_values.get("max_tokens")
        max_tokens = int(tokens_val.value) if tokens_val is not None else 4096

        project_name_val = config_values.get("project_name")
        project_name = (
            str(project_name_val.value) if project_name_val is not None else ""
        )

        model_val = config_values.get("model")
        model = str(model_val.value) if model_val is not None else ""

        return WorkspaceSettings(
            project_name=project_name,
            spells_enabled=spells_enabled,
            contemplation_level=contemplation_level,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    def save_workspace_settings(
        self, project_dir: Path, settings: WorkspaceSettings
    ) -> None:
        cm = ConfigManager(project_dir=project_dir)
        to_save: dict[str, Any] = {
            "spells_enabled": list(settings.spells_enabled),
            "contemplation_level": settings.contemplation_level,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        if settings.project_name:
            to_save["project_name"] = settings.project_name
        if settings.model:
            to_save["model"] = settings.model
        cm.save_project_config(to_save)
