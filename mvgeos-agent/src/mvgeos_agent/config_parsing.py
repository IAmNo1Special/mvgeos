"""Standalone config coercion for agent construction.

Owns all read-side coercion of resolved configuration values:
temperature, max_tokens, contemplation level/budget, queue mode,
spell names, and rune paths resolution.

This is deliberately lenient (warn + fall back to defaults) and is
separate from ``ConfigManager.validate_value`` which raises on write.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mvgeos_agent.config_manager import ConfigLayer, ConfigValue
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL,
    resolve_rune_paths,
)
from mvgeos_agent.types import QueueMode

logger = logging.getLogger(__name__)

ConfigGetter = Callable[[str, Any], Any]

_VALID_CONTEMPLATION_LEVELS = ("none", "low", "medium", "high")


@dataclass(frozen=True)
class AgentConfig:
    """Fully coerced agent configuration values."""

    model_id: str
    temperature: float
    max_tokens: int
    contemplation_level: str
    contemplation_budget: int | None
    exclude_contemplation: bool
    queue_mode: QueueMode
    spell_names: list[str] | None
    runes_paths: list[Path]


class ConfigParsing:
    """Coerces raw resolved config into a validated :class:`AgentConfig`."""

    @classmethod
    def resolve(
        cls,
        config: Mapping[str, ConfigValue],
        *,
        agent_name: str = DEFAULT_AGENT_NAME,
        extension_dir: str | None = None,
        runes_paths: Sequence[str] | None = None,
    ) -> AgentConfig:
        """Resolve and coerce all config values into an AgentConfig."""

        def _get(key: str, default: Any) -> Any:
            return config.get(key, ConfigValue(default, ConfigLayer.DEFAULTS)).value

        return AgentConfig(
            model_id=cls._parse_model(_get),
            temperature=cls._parse_temperature(_get),
            max_tokens=cls._parse_max_tokens(_get),
            contemplation_level=cls._parse_contemplation_level(_get),
            contemplation_budget=cls._parse_contemplation_budget(_get),
            exclude_contemplation=bool(_get("exclude_contemplation", False)),
            queue_mode=cls._parse_queue_mode(_get),
            spell_names=cls._parse_spell_names(_get),
            runes_paths=cls._parse_runes_paths(
                _get,
                agent_name=agent_name,
                extension_dir=extension_dir,
                runes_paths=runes_paths,
            ),
        )

    @staticmethod
    def _parse_model(_get: ConfigGetter) -> str:
        return str(_get("model", DEFAULT_MODEL))

    @staticmethod
    def _parse_temperature(_get: ConfigGetter) -> float:
        raw_temp = _get("temperature", 0.7)
        try:
            if isinstance(raw_temp, bool):
                raise TypeError("temperature cannot be boolean")
            return float(raw_temp)
        except ValueError, TypeError:
            logger.warning(
                "Invalid temperature in config (%r); falling back to default %s",
                raw_temp,
                0.7,
            )
            return 0.7

    @staticmethod
    def _parse_max_tokens(_get: ConfigGetter) -> int:
        raw_max_tokens = _get("max_tokens", 4096)
        try:
            if isinstance(raw_max_tokens, bool):
                raise TypeError("max_tokens cannot be boolean")
            return int(raw_max_tokens)
        except ValueError, TypeError:
            logger.warning(
                "Invalid max_tokens in config (%r); falling back to default %s",
                raw_max_tokens,
                4096,
            )
            return 4096

    @staticmethod
    def _parse_contemplation_level(_get: ConfigGetter) -> str:
        raw_level = str(_get("contemplation_level", "medium"))
        if raw_level in _VALID_CONTEMPLATION_LEVELS:
            return raw_level
        logger.warning(
            "Invalid contemplation_level in config (%r); "
            "falling back to default 'medium'",
            raw_level,
        )
        return "medium"

    @staticmethod
    def _parse_contemplation_budget(_get: ConfigGetter) -> int | None:
        raw_budget = _get("contemplation_budget", None)
        if raw_budget is None:
            return None
        try:
            if isinstance(raw_budget, bool):
                raise TypeError("contemplation_budget cannot be boolean")
            return int(raw_budget)
        except ValueError, TypeError:
            logger.warning(
                "Invalid contemplation_budget in config (%r); "
                "falling back to default None",
                raw_budget,
            )
            return None

    @staticmethod
    def _parse_queue_mode(_get: ConfigGetter) -> QueueMode:
        raw_queue = _get("queue_mode", QueueMode.ONE_AT_A_TIME)
        if isinstance(raw_queue, QueueMode):
            return raw_queue
        try:
            return QueueMode(str(raw_queue))
        except ValueError:
            logger.warning(
                "Invalid queue_mode in config (%r); "
                "falling back to default 'one-at-a-time'",
                raw_queue,
            )
            return QueueMode.ONE_AT_A_TIME

    @staticmethod
    def _parse_spell_names(_get: ConfigGetter) -> list[str] | None:
        spells_enabled = _get("spells_enabled", [])
        return list(spells_enabled) if spells_enabled else None

    @staticmethod
    def _parse_runes_paths(
        _get: ConfigGetter,
        *,
        agent_name: str,
        extension_dir: str | None,
        runes_paths: Sequence[str] | None,
    ) -> list[Path]:
        if runes_paths is not None:
            return [Path(str(p)).expanduser() for p in runes_paths]
        rune_paths_config = _get("rune_paths", None)
        if rune_paths_config:
            return [Path(str(p)).expanduser() for p in rune_paths_config]
        return resolve_rune_paths(agent_name, extension_dir)
