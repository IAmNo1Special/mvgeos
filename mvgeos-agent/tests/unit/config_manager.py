from __future__ import annotations

import json
from pathlib import Path

from mvgeos_agent.config_manager import (
    ConfigLayer,
    ConfigManager,
)


def _make_mgr(tmp_path: Path, agent_name: str = "test-agent") -> ConfigManager:
    """Create a ConfigManager with isolated paths for testing."""
    return ConfigManager(
        agent_name=agent_name,
        project_dir=tmp_path,
        agent_config_base=tmp_path / "agent_configs",
    )


class TestConfigManagerDefaults:
    def test_defaults_are_used_when_no_files_exist(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        merged = mgr.load()
        assert merged["model"].value == ConfigManager.DEFAULTS["model"]
        assert merged["max_tokens"].value == ConfigManager.DEFAULTS["max_tokens"]
        assert merged["model"].layer == ConfigLayer.DEFAULTS

    def test_defaults_can_be_overridden(self, tmp_path: Path) -> None:
        custom_defaults = {"model": "custom-model", "max_tokens": 100}
        mgr = ConfigManager(
            agent_name="test-agent",
            project_dir=tmp_path,
            defaults=custom_defaults,
            agent_config_base=tmp_path / "agent_configs",
        )
        merged = mgr.load()
        assert merged["model"].value == "custom-model"


class TestConfigManagerProvenance:
    def test_provenance_defaults(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        merged = mgr.load()
        for key in ConfigManager.DEFAULTS:
            assert merged[key].layer == ConfigLayer.DEFAULTS

    def test_provenance_agent_scope(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        mgr.agent_config_path.write_text(
            json.dumps({"model": "agent-model"}), encoding="utf-8"
        )
        merged = mgr.load()
        assert merged["model"].value == "agent-model"
        assert merged["model"].layer == ConfigLayer.AGENT

    def test_provenance_legacy(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        legacy_dir = tmp_path / ".agents" / ".mvgeos"
        legacy_dir.mkdir(parents=True)
        legacy_dir.joinpath("config.json").write_text(
            json.dumps({"model": "legacy-model"}), encoding="utf-8"
        )
        merged = mgr.load()
        assert merged["model"].value == "legacy-model"
        assert merged["model"].layer == ConfigLayer.LEGACY

    def test_provenance_constructor_overrides(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr_with_overrides = mgr.with_overrides(model="override-model")
        merged = mgr_with_overrides.load()
        assert merged["model"].value == "override-model"
        assert merged["model"].layer == ConfigLayer.CONSTRUCTOR


class TestConfigManagerPrecedence:
    def test_agent_overrides_defaults(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        mgr.agent_config_path.write_text(
            json.dumps({"model": "agent-model"}), encoding="utf-8"
        )
        merged = mgr.load()
        assert merged["model"].value == "agent-model"
        assert merged["model"].layer == ConfigLayer.AGENT

    def test_legacy_overrides_agent(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        mgr.agent_config_path.write_text(
            json.dumps({"model": "agent-model"}), encoding="utf-8"
        )
        legacy_dir = tmp_path / ".agents" / ".mvgeos"
        legacy_dir.mkdir(parents=True)
        legacy_dir.joinpath("config.json").write_text(
            json.dumps({"model": "legacy-model"}), encoding="utf-8"
        )
        merged = mgr.load()
        assert merged["model"].value == "legacy-model"
        assert merged["model"].layer == ConfigLayer.LEGACY

    def test_constructor_overrides_all(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        mgr.agent_config_path.write_text(
            json.dumps({"model": "agent-model"}), encoding="utf-8"
        )
        legacy_dir = tmp_path / ".agents" / ".mvgeos"
        legacy_dir.mkdir(parents=True)
        legacy_dir.joinpath("config.json").write_text(
            json.dumps({"model": "legacy-model"}), encoding="utf-8"
        )
        mgr_with_overrides = mgr.with_overrides(model="constructor-model")
        merged = mgr_with_overrides.load()
        assert merged["model"].value == "constructor-model"
        assert merged["model"].layer == ConfigLayer.CONSTRUCTOR

    def test_mixed_provenance(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        mgr.agent_config_path.write_text(
            json.dumps({"model": "agent-model"}), encoding="utf-8"
        )
        merged = mgr.load()
        # model comes from agent, max_tokens from defaults
        assert merged["model"].layer == ConfigLayer.AGENT
        assert merged["max_tokens"].layer == ConfigLayer.DEFAULTS

    def test_deep_merge_nested_dicts(self, tmp_path: Path) -> None:
        """Deep merge preserves sibling keys from lower layers."""
        mgr = ConfigManager(
            agent_name="test-agent",
            project_dir=tmp_path,
            defaults={
                "settings": {"a": 1, "b": 2},
                "model": "default-model",
            },
            agent_config_base=tmp_path / "agent_configs",
        )
        mgr.agent_config_path.parent.mkdir(parents=True, exist_ok=True)
        mgr.agent_config_path.write_text(
            json.dumps({"settings": {"b": 99, "c": 3}}), encoding="utf-8"
        )
        merged = mgr.load()
        # Deep merge: agent's "settings" overrides leaf keys only
        assert merged["settings"].value == {"a": 1, "b": 99, "c": 3}


class TestConfigManagerAgentScope:
    def test_ensure_agent_config_seeds_defaults(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        result = mgr.ensure_agent_config()
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data == ConfigManager.DEFAULTS

    def test_ensure_agent_config_idempotent(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.ensure_agent_config()
        mgr.agent_config_path.write_text(
            json.dumps({"model": "custom"}), encoding="utf-8"
        )
        mgr.ensure_agent_config()
        data = json.loads(mgr.agent_config_path.read_text(encoding="utf-8"))
        assert data["model"] == "custom"

    def test_set_writes_to_agent_scope(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.set("model", "new-model")
        data = json.loads(mgr.agent_config_path.read_text(encoding="utf-8"))
        assert data["model"] == "new-model"

    def test_reset_clears_agent_scope(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        mgr.set("model", "custom-model")
        mgr.reset()
        data = json.loads(mgr.agent_config_path.read_text(encoding="utf-8"))
        assert data == ConfigManager.DEFAULTS

    def test_get_single_value_with_provenance(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        val = mgr.get("model")
        assert val.value == ConfigManager.DEFAULTS["model"]
        assert val.layer == ConfigLayer.DEFAULTS


class TestConfigManagerConfigFileLocations:
    def test_agent_config_path_uses_agent_name(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path, agent_name="my-agent")
        assert "my-agent" in str(mgr.agent_config_path)
        assert str(mgr.agent_config_path).endswith("config.json")

    def test_legacy_config_path_in_project(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        assert str(mgr.legacy_config_path) == str(
            tmp_path / ".agents" / ".mvgeos" / "config.json"
        )
