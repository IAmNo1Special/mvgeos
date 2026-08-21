from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from mvgeos_agent.config_manager import ConfigLayer, ConfigValue
from mvgeos_agent.config_parsing import AgentConfig, ConfigParsing
from mvgeos_agent.constants import DEFAULT_AGENT_NAME, DEFAULT_MODEL, resolve_rune_paths
from mvgeos_agent.types import QueueMode


def _cfg(**kwargs: Any) -> dict[str, ConfigValue]:
    return {k: ConfigValue(v, ConfigLayer.DEFAULTS) for k, v in kwargs.items()}


class TestAgentConfigDefaults:
    def test_empty_config_yields_defaults(self) -> None:
        cfg = ConfigParsing.resolve({})
        assert cfg.model_id == DEFAULT_MODEL
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 4096
        assert cfg.contemplation_level == "medium"
        assert cfg.contemplation_budget is None
        assert cfg.exclude_contemplation is False
        assert cfg.queue_mode is QueueMode.ONE_AT_A_TIME
        assert cfg.spell_names is None
        assert cfg.runes_paths == resolve_rune_paths(DEFAULT_AGENT_NAME, None)

    def test_agent_config_is_frozen(self) -> None:
        cfg = ConfigParsing.resolve({})
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.temperature = 0.1  # type: ignore[misc]


class TestValidCoercion:
    def test_int_temperature_coerced_to_float(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(temperature=0))
        assert cfg.temperature == 0.0
        assert isinstance(cfg.temperature, float)

    def test_numeric_string_max_tokens_coerced(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(max_tokens="2048"))
        assert cfg.max_tokens == 2048

    def test_float_max_tokens_coerced(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(max_tokens=8192.0))
        assert cfg.max_tokens == 8192

    def test_string_budget_coerced(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(contemplation_budget="512"))
        assert cfg.contemplation_budget == 512

    def test_truthy_exclude_contemplation(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(exclude_contemplation=1))
        assert cfg.exclude_contemplation is True

    def test_non_string_model_coerced(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(model=12345))
        assert cfg.model_id == "12345"

    def test_queue_mode_string_coerced(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(queue_mode="all"))
        assert cfg.queue_mode is QueueMode.ALL

    def test_queue_mode_enum_passes_through(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(queue_mode=QueueMode.ALL))
        assert cfg.queue_mode is QueueMode.ALL


class TestInvalidValuesFallBack:
    def test_boolean_temperature_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(temperature=True))
        assert cfg.temperature == 0.7

    def test_garbage_temperature_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(temperature="invalid"))
        assert cfg.temperature == 0.7

    def test_boolean_max_tokens_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(max_tokens=True))
        assert cfg.max_tokens == 4096

    def test_none_max_tokens_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(max_tokens=None))
        assert cfg.max_tokens == 4096

    def test_unknown_contemplation_level_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(contemplation_level="ultra_high"))
        assert cfg.contemplation_level == "medium"

    def test_list_budget_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(contemplation_budget=[1, 2]))
        assert cfg.contemplation_budget is None

    def test_boolean_budget_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(contemplation_budget=True))
        assert cfg.contemplation_budget is None

    def test_invalid_queue_mode_falls_back(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(queue_mode="bogus"))
        assert cfg.queue_mode is QueueMode.ONE_AT_A_TIME


class TestSpellNames:
    def test_non_empty_list_preserved(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(spells_enabled=["bash", "read"]))
        assert cfg.spell_names == ["bash", "read"]

    def test_input_list_copied(self) -> None:
        spells = ["bash"]
        cfg = ConfigParsing.resolve(_cfg(spells_enabled=spells))
        spells.append("write")
        assert cfg.spell_names == ["bash"]

    def test_empty_list_normalized_to_none(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(spells_enabled=[]))
        assert cfg.spell_names is None

    def test_missing_key_yields_none(self) -> None:
        cfg = ConfigParsing.resolve({})
        assert cfg.spell_names is None


class TestRunesPathsResolution:
    def test_constructor_arg_wins_over_config(self) -> None:
        cfg = ConfigParsing.resolve(
            _cfg(rune_paths=["/from/config"]),
            runes_paths=["/from/ctor"],
        )
        assert cfg.runes_paths == [Path("/from/ctor")]

    def test_config_key_used_without_constructor_arg(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(rune_paths=["/from/config"]))
        assert cfg.runes_paths == [Path("/from/config")]

    def test_tilde_expanded(self) -> None:
        cfg = ConfigParsing.resolve(_cfg(rune_paths=["~/runes"]))
        assert cfg.runes_paths == [Path("~/runes").expanduser()]

    def test_default_resolves_agent_name_and_extension_dir(self) -> None:
        cfg = ConfigParsing.resolve({}, agent_name="my-agent", extension_dir="/ext")
        assert cfg.runes_paths == resolve_rune_paths("my-agent", "/ext")


class TestBaseMvgeParity:
    def test_base_mvge_matches_config_parsing(self, tmp_path: Path) -> None:
        from mvgeos_agent.base_mvge import BaseMvge
        from mvgeos_agent.environment import MvgeEnvironment

        custom_defaults = {
            "model": "parity-model",
            "temperature": "invalid",
            "max_tokens": "2048",
            "contemplation_level": "high",
            "contemplation_budget": "256",
            "exclude_contemplation": True,
            "spells_enabled": ["bash", "read"],
            "rune_paths": [str(tmp_path / "runes")],
        }
        mgr = _parity_mgr(tmp_path, custom_defaults)
        env = MvgeEnvironment.resolve(
            "test-agent",
            project_dir=tmp_path,
            config_manager=mgr,
        )
        agent = BaseMvge(api_key="test-key", environment=env)
        cfg = ConfigParsing.resolve(env.config)

        assert isinstance(cfg, AgentConfig)
        assert agent._model_id == cfg.model_id
        assert agent._temperature == cfg.temperature
        assert agent._max_tokens == cfg.max_tokens
        assert agent._contemplation_level == cfg.contemplation_level
        assert agent._contemplation_budget == cfg.contemplation_budget
        assert agent._exclude_contemplation == cfg.exclude_contemplation
        assert agent._queue_mode == cfg.queue_mode
        assert agent._spell_names == cfg.spell_names
        assert agent._runes_paths == cfg.runes_paths


def _parity_mgr(tmp_path: Path, defaults: dict[str, Any]) -> Any:
    from mvgeos_agent.config_manager import ConfigManager

    return ConfigManager(
        agent_name="test-agent",
        project_dir=tmp_path,
        defaults=defaults,
        agent_config_base=tmp_path / "agent_configs",
    )
