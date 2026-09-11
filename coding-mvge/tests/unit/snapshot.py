from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mvgeos_agent import Mvge
from mvgeos_agent.config_manager import ConfigManager
from mvgeos_agent.environment import MvgeEnvironment, PromptSource
from mvgeos_core.constants import DEFAULT_MODEL
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    RuneContext,
    RuneLoad,
    RuneManifest,
    RuneScope,
    SigilHook,
    SkillDiagnostic,
    SkillDiagnosticKind,
    SkillLoad,
    SkillManifest,
    SkillScope,
    SpellDefinition,
)

from coding_mvge import root_mvge
from coding_mvge.spells import bash, read


def _make_runner() -> RuneRunner:
    runner = RuneRunner()
    runner.bind_context(
        RuneContext(cwd="/tmp", mode="cli", agent_name="test-agent", api_key="key")
    )
    return runner


class TestBuildSnapshotNoRunes:
    def test_builtin_spells_only(self, tmp_path: Path) -> None:
        agent = Mvge(api_key="key", name="test-agent", spells=[bash, read])
        snap = agent.build_snapshot()

        assert snap.agent_name == "test-agent"
        assert snap.model == DEFAULT_MODEL
        assert len(snap.spells) == 2
        assert all(s.source == "builtin" for s in snap.spells)
        assert {s.name for s in snap.spells} == {"bash", "read"}

    def test_no_runner_empty_collections(self, tmp_path: Path) -> None:
        agent = Mvge(api_key="key", name="test-agent", spells=[])
        snap = agent.build_snapshot()

        assert snap.runes == []
        assert snap.skills == []
        assert snap.diagnostics == []

    def test_default_spells(self) -> None:
        snap = root_mvge.build_snapshot()
        assert len(snap.spells) == 9
        names = {s.name for s in snap.spells}
        assert names == {
            "bash",
            "read",
            "write",
            "edit",
            "find",
            "list_files",
            "grep",
            "search_web",
            "read_url",
        }


class TestBuildSnapshotWithRunner:
    @pytest.mark.asyncio
    async def test_runes_and_spells_with_provenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))

        agent = Mvge(
            api_key="key",
            name="test-agent",
            spells=[bash],
        )
        runner = _make_runner()

        manifest = RuneManifest(
            name="my_rune",
            version="1.2.3",
            description="A test rune",
            scope=RuneScope.USER,
            path=str(tmp_path / "my_rune"),
            enabled=True,
            entry_point="main.py",
            hooks=[SigilHook.TURN_START, SigilHook.AFTER_INVOCATION],
        )

        def factory(api: Any) -> None:
            api.register_spell(
                SpellDefinition(
                    name="custom_tool",
                    description="A custom tool from rune",
                    parameters={"type": "object", "properties": {}},
                    source_rune="my_rune",
                )
            )

        load = RuneLoad(manifest=manifest, factory=factory)
        await runner.load_rune_loads([load])

        agent._runner = runner
        agent._config_manager = ConfigManager(
            agent_name="test-agent",
            project_dir=tmp_path,
            agent_config_base=tmp_path / "agent_configs",
        )

        snap = agent.build_snapshot()

        assert snap.model == DEFAULT_MODEL

        spell_map = {s.name: s for s in snap.spells}
        assert "bash" in spell_map
        assert spell_map["bash"].source == "builtin"
        assert "custom_tool" in spell_map
        assert spell_map["custom_tool"].source == "rune"
        assert spell_map["custom_tool"].source_rune == "my_rune"

        assert len(snap.runes) == 1
        rune = snap.runes[0]
        assert rune.name == "my_rune"
        assert rune.version == "1.2.3"
        assert rune.scope == "user"
        assert rune.enabled is True
        assert SigilHook.TURN_START.value in rune.hooks
        assert SigilHook.AFTER_INVOCATION.value in rune.hooks

    @pytest.mark.asyncio
    async def test_skills_included(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        agent = Mvge(api_key="key", name="test-agent", spells=[])
        runner = _make_runner()

        skill = SkillManifest(
            name="test-skill",
            description="A test skill",
            scope=SkillScope.PROJECT,
            path=str(tmp_path / "test-skill"),
            version="0.5.0",
            license="MIT",
            compatibility="Python 3.14+",
            allowed_tools="read write",
            disable_model_invocation=False,
        )
        runner.load_skills([SkillLoad(manifest=skill)])

        agent._runner = runner
        snap = agent.build_snapshot()

        assert len(snap.skills) == 1
        s = snap.skills[0]
        assert s.name == "test-skill"
        assert s.scope == "project"
        assert s.version == "0.5.0"
        assert s.license == "MIT"
        assert s.allowed_tools == "read write"

    @pytest.mark.asyncio
    async def test_diagnostics_included(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        agent = Mvge(api_key="key", name="test-agent", spells=[])
        runner = _make_runner()

        rune_diag = Diagnostic(
            kind=DiagnosticKind.SHADOWED_RUNE,
            rune_name="dup_rune",
            message="shadowed by user scope",
            scope=RuneScope.USER,
            path="/tmp/dup_rune",
        )
        skill_diag = SkillDiagnostic(
            kind=SkillDiagnosticKind.PARSE_WARNING,
            skill_name="bad_skill",
            message="could not parse SKILL.md",
            scope=SkillScope.PROJECT,
            path="/tmp/bad_skill",
        )

        await runner.load_rune_loads([], diagnostics=[rune_diag])
        runner.load_skills([], diagnostics=[skill_diag])

        agent._runner = runner
        snap = agent.build_snapshot()

        assert len(snap.diagnostics) == 2
        targets = {d.target for d in snap.diagnostics}
        assert "rune" in targets
        assert "skill" in targets

        rune_diags = [d for d in snap.diagnostics if d.target == "rune"]
        assert len(rune_diags) == 1
        assert rune_diags[0].name == "dup_rune"
        assert rune_diags[0].kind == "shadowed_rune"

        skill_diags = [d for d in snap.diagnostics if d.target == "skill"]
        assert len(skill_diags) == 1
        assert skill_diags[0].name == "bad_skill"
        assert skill_diags[0].kind == "parse_warning"


class TestBuildSnapshotWithConfig:
    def test_config_values_with_provenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))

        config_mgr = ConfigManager(
            agent_name="test-agent",
            project_dir=tmp_path,
            agent_config_base=tmp_path / "agent_configs",
        )
        config_mgr.set("model", "custom-model")

        env = MvgeEnvironment.resolve("test-agent", config_manager=config_mgr)
        agent = Mvge(
            api_key="key",
            name="test-agent",
            environment=env,
        )

        snap = agent.build_snapshot()

        assert snap.model == "custom-model"
        config_dict = {c.key: c for c in snap.config}
        assert config_dict["model"].value == "custom-model"
        assert config_dict["model"].layer == "agent"

        assert config_dict["max_tokens"].layer == "defaults"
        assert config_dict["max_tokens"].source_file is None

    def test_no_config_manager_empty_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        env = MvgeEnvironment.resolve("test-agent", has_config_manager=False)
        agent = Mvge(
            api_key="key",
            name="test-agent",
            spells=[],
            environment=env,
        )
        snap = agent.build_snapshot()
        assert snap.config == []


class TestBuildSnapshotPrompt:
    def test_prompt_resolved_from_config_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        (tmp_path / "SYSTEM.md").write_text("Custom system from file", encoding="utf-8")

        agent = Mvge(api_key="key", name="test-agent", spells=[])
        snap = agent.build_snapshot()

        assert snap.prompt.text == "Custom system from file"
        assert snap.prompt.source == PromptSource.AGENT_MD.value

    def test_prompt_builtin_when_no_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        agent = Mvge(api_key="key", name="test-agent", spells=[])
        snap = agent.build_snapshot()
        assert snap.prompt.source == PromptSource.BUILTIN.value


class TestBuildSnapshotSerialisation:
    def test_to_json_round_trip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        agent = Mvge(
            api_key="key",
            name="test-agent",
            spells=[bash, read],
        )
        snap = agent.build_snapshot()

        json_str = snap.to_json()
        parsed = json.loads(json_str)

        assert parsed["agent_name"] == "test-agent"
        assert parsed["model"] == DEFAULT_MODEL
        assert len(parsed["spells"]) == 2
        assert all(s["source"] == "builtin" for s in parsed["spells"])

    def test_to_dict_returns_serialisable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        agent = Mvge(api_key="key", name="test-agent", spells=[bash])
        snap = agent.build_snapshot()

        d = snap.to_dict()
        assert isinstance(d, dict)
        assert d["agent_name"] == "test-agent"
        assert isinstance(d["spells"], list)

    @pytest.mark.asyncio
    async def test_to_json_with_runes_and_diagnostics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Mvge, "config_dir", property(lambda self: tmp_path))
        agent = Mvge(api_key="key", name="test-agent", spells=[])
        runner = _make_runner()

        manifest = RuneManifest(
            name="r1",
            version="1.0.0",
            description="r1",
            scope=RuneScope.PROJECT,
            path="/tmp/r1",
            enabled=True,
        )

        def factory(api: Any) -> None:
            api.register_spell(
                SpellDefinition(name="spell1", description="s1", source_rune="r1")
            )

        await runner.load_rune_loads(
            [RuneLoad(manifest=manifest, factory=factory)],
            diagnostics=[
                Diagnostic(
                    kind=DiagnosticKind.PARSE_WARNING,
                    rune_name="bad_rune",
                    message="bad json",
                    scope=RuneScope.USER,
                    path="/tmp/bad_rune",
                )
            ],
        )

        agent._runner = runner
        snap = agent.build_snapshot()

        json_str = snap.to_json()
        parsed = json.loads(json_str)

        assert len(parsed["runes"]) == 1
        assert parsed["runes"][0]["name"] == "r1"
        assert len(parsed["diagnostics"]) == 1
        assert parsed["diagnostics"][0]["target"] == "rune"
        assert len(parsed["spells"]) == 1
        assert parsed["spells"][0]["source"] == "rune"
        assert parsed["spells"][0]["source_rune"] == "r1"
