from __future__ import annotations

import copy
import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple

from mvgeos_agent.constants import DEFAULT_AGENT_NAME, DEFAULT_MODEL

logger = logging.getLogger(__name__)

AGENT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def is_known_agent(
    agent_name: str,
    *,
    agent_config_base: Path | None = None,
    project_dir: Path | None = None,
) -> bool:
    """Check whether an agent name is valid/known.

    An agent is known if it matches DEFAULT_AGENT_NAME ("default-mvge")
    or if its agent-scope directory or config file exists.
    """
    if not isinstance(agent_name, str) or not AGENT_NAME_PATTERN.match(agent_name):
        return False

    if agent_name in (
        DEFAULT_AGENT_NAME,
        "coding-mvge",
        "coding_mvge",
        "test-agent",
    ):
        return True

    base = (
        agent_config_base.expanduser()
        if agent_config_base is not None
        else Path("~/.agents/.mvgeos").expanduser()
    )
    agent_dir = base / agent_name
    if agent_dir.exists():
        return True

    proj_dir = project_dir or Path.cwd()
    proj_agent_dir = proj_dir / ".agents" / ".mvgeos" / agent_name
    return proj_agent_dir.exists()


def validate_agent_name(
    agent_name: str,
    *,
    agent_config_base: Path | None = None,
    project_dir: Path | None = None,
    allow_create: bool = False,
) -> None:
    """Validate that an agent name exists and is syntactically valid.

    Raises ValueError with an actionable message if invalid or unknown.
    """
    if not isinstance(agent_name, str) or not AGENT_NAME_PATTERN.match(agent_name):
        raise ValueError(
            f"Invalid agent name '{agent_name}'. Agent names must contain "
            "only alphanumeric characters, dashes, and underscores."
        )

    if allow_create:
        return

    if is_known_agent(
        agent_name, agent_config_base=agent_config_base, project_dir=project_dir
    ):
        return

    base = (
        agent_config_base.expanduser()
        if agent_config_base is not None
        else Path("~/.agents/.mvgeos").expanduser()
    )
    agent_dir = base / agent_name
    raise ValueError(
        f"Unknown agent '{agent_name}'. Agent configuration or directory "
        f"does not exist at '{agent_dir}'. Configure it with "
        f"'mvgeos config set --agent-name {agent_name} <key> <value>'."
    )


class ConfigLayer(Enum):
    """Indicates which layer a resolved config value came from.

    Precedence from lowest to highest:
    DEFAULTS < AGENT < LEGACY < CONSTRUCTOR
    """

    DEFAULTS = "defaults"
    AGENT = "agent"
    LEGACY = "legacy"
    CONSTRUCTOR = "constructor"


class ConfigValue(NamedTuple):
    """A resolved config value with provenance."""

    value: Any
    layer: ConfigLayer


class ConfigManager:
    """Layered config loader with deep-merge and provenance tracking.

    Precedence (highest to lowest):
    1. Constructor overrides (via ``with_overrides()``)
    2. Legacy project config (``.agents/.mvgeos/config.json``)
    3. Agent-scope file (``~/.agents/.mvgeos/{name}/config.json``)
    4. Defaults

    Each resolved value carries the layer it came from.
    """

    DEFAULTS: dict[str, Any] = {
        "model": DEFAULT_MODEL,
        "max_tokens": 4096,
        "temperature": 0.7,
        "contemplation_level": "medium",
        "spells_enabled": ["bash", "read", "write", "edit", "find", "list", "grep"],
    }

    def __init__(
        self,
        agent_name: str = DEFAULT_AGENT_NAME,
        project_dir: Path | None = None,
        defaults: dict[str, Any] | None = None,
        agent_config_base: Path | None = None,
    ) -> None:
        self._agent_name = agent_name
        self._project_dir = project_dir or Path.cwd()
        self._defaults = defaults if defaults is not None else self.DEFAULTS
        self._constructor_overrides: dict[str, Any] = {}
        self._agent_config_base = (
            agent_config_base.expanduser()
            if agent_config_base is not None
            else Path("~/.agents/.mvgeos").expanduser()
        )

    @property
    def agent_config_path(self) -> Path:
        """Path to the agent-scope config file."""
        return self._agent_config_base / self._agent_name / "config.json"

    @property
    def legacy_config_path(self) -> Path:
        """Path to the legacy project config file."""
        return self._project_dir / ".agents" / ".mvgeos" / "config.json"

    def with_overrides(self, **kwargs: Any) -> ConfigManager:
        """Return a new manager with constructor-level overrides applied.

        These take precedence over all file-based layers.
        """
        new_mgr = copy.copy(self)
        new_mgr._constructor_overrides = dict(kwargs)
        return new_mgr

    def load(self) -> dict[str, ConfigValue]:
        """Load and merge config from all layers, returning provenance.

        Nested dicts are deep-merged: a higher layer only overrides the
        leaf keys it provides, preserving sibling keys from lower layers.
        Provenance is tracked per top-level key using the highest layer
        that contributed to that key.
        """
        # Layer 1: Defaults (lowest precedence)
        merged: dict[str, Any] = self._deep_merge({}, self._defaults)
        layers: dict[str, ConfigLayer] = dict.fromkeys(
            self._defaults, ConfigLayer.DEFAULTS
        )

        # Layer 2: Agent-scope file
        agent_data = self._load_json(self.agent_config_path)
        merged = self._deep_merge(merged, agent_data)
        for key in agent_data:
            layers[key] = ConfigLayer.AGENT

        # Layer 3: Legacy project config
        legacy_data = self._load_json(self.legacy_config_path)
        merged = self._deep_merge(merged, legacy_data)
        for key in legacy_data:
            layers[key] = ConfigLayer.LEGACY

        # Layer 4: Constructor overrides (highest precedence)
        merged = self._deep_merge(merged, self._constructor_overrides)
        for key in self._constructor_overrides:
            layers[key] = ConfigLayer.CONSTRUCTOR

        return {key: ConfigValue(merged[key], layers[key]) for key in merged}

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge override into base, returning a new dict."""
        result = dict(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    KNOWN_KEYS: set[str] = {
        "model",
        "max_tokens",
        "temperature",
        "contemplation_level",
        "contemplation_budget",
        "exclude_contemplation",
        "spells_enabled",
        "rune_paths",
        "project_name",
    }

    @classmethod
    def validate_value(cls, key: str, value: Any) -> Any:
        """Validate a config key and value against the schema.

        Returns the coerced/validated value or raises ValueError.
        """
        if key not in cls.KNOWN_KEYS:
            raise ValueError(f"Unknown configuration key: '{key}'")

        if key == "project_name":
            if not isinstance(value, str):
                raise ValueError("Invalid project_name value: expected string")
            return value

        if key == "temperature":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError("Invalid temperature value: expected float")
            try:
                val_float = float(value)
            except ValueError, TypeError:
                raise ValueError("Invalid temperature value: expected float") from None
            if val_float < 0.0 or val_float > 2.0:
                raise ValueError(
                    "Invalid temperature value: expected float between 0.0 and 2.0"
                )
            return val_float

        if key == "max_tokens":
            if isinstance(value, bool):
                raise ValueError("Invalid max_tokens value: expected int")
            if isinstance(value, str):
                try:
                    val_int = int(value)
                except ValueError, TypeError:
                    raise ValueError("Invalid max_tokens value: expected int") from None
            elif isinstance(value, int):
                val_int = value
            elif isinstance(value, float) and value.is_integer():
                val_int = int(value)
            else:
                raise ValueError("Invalid max_tokens value: expected int")
            if val_int <= 0:
                raise ValueError("Invalid max_tokens value: expected positive integer")
            return val_int

        if key == "model":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid model value: expected string")
            return value

        if key == "contemplation_level":
            if not isinstance(value, str) or value not in (
                "none",
                "low",
                "medium",
                "high",
            ):
                raise ValueError(
                    "Invalid contemplation_level value: expected one of "
                    "['none', 'low', 'medium', 'high']"
                )
            return value

        if key == "contemplation_budget":
            if value is None:
                return None
            if isinstance(value, bool):
                raise ValueError(
                    "Invalid contemplation_budget value: expected integer >= 0 or null"
                )
            if isinstance(value, str):
                try:
                    val_int = int(value)
                except ValueError, TypeError:
                    raise ValueError(
                        "Invalid contemplation_budget value: "
                        "expected integer >= 0 or null"
                    ) from None
            elif isinstance(value, int):
                val_int = value
            else:
                raise ValueError(
                    "Invalid contemplation_budget value: expected integer >= 0 or null"
                )
            if val_int < 0:
                raise ValueError(
                    "Invalid contemplation_budget value: expected integer >= 0 or null"
                )
            return val_int

        if key == "exclude_contemplation":
            if not isinstance(value, bool):
                raise ValueError("Invalid exclude_contemplation value: expected bool")
            return value

        if key in ("spells_enabled", "rune_paths"):
            if not isinstance(value, list) or not all(
                isinstance(x, str) for x in value
            ):
                raise ValueError(f"Invalid {key} value: expected list of strings")
            return value

        return value

    def get(self, key: str, default: Any = None) -> ConfigValue:
        """Get a single config value with provenance."""
        merged = self.load()
        if key in merged:
            return merged[key]
        return ConfigValue(default, ConfigLayer.DEFAULTS)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the agent-scope config file."""
        validated_value = self.validate_value(key, value)
        self.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._load_json(self.agent_config_path)
        data[key] = validated_value
        self.agent_config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def set_project(self, key: str, value: Any) -> None:
        """Set a value in the project-scope config file."""
        validated_value = self.validate_value(key, value)
        self.legacy_config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._load_json(self.legacy_config_path)
        data[key] = validated_value
        self.legacy_config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save_project_config(self, values: dict[str, Any]) -> None:
        """Save multiple validated values to the project-scope config file."""
        self.legacy_config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._load_json(self.legacy_config_path)
        for key, value in values.items():
            data[key] = self.validate_value(key, value)
        self.legacy_config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_project_config(self) -> dict[str, Any]:
        """Load the raw project-scope config dictionary."""
        return self._load_json(self.legacy_config_path)

    def reset(self) -> None:
        """Reset agent-scope config to defaults."""
        self.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.agent_config_path.write_text(
            json.dumps(self._defaults, indent=2), encoding="utf-8"
        )

    def ensure_agent_config(self) -> Path:
        """Create agent-scope config with seeded defaults if absent.

        Returns the path to the config file.
        """
        if self.agent_config_path.exists():
            return self.agent_config_path
        self.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.agent_config_path.write_text(
            json.dumps(self._defaults, indent=2), encoding="utf-8"
        )
        return self.agent_config_path

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        """Load JSON from a path, returning empty dict on any error."""
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return data
        except json.JSONDecodeError, OSError:
            return {}
