from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    BeforeMvgeStartData,
    Diagnostic,
    DiagnosticKind,
    RuneScope,
    SigilHook,
)

from mvgeos_agent.config_manager import ConfigLayer, ConfigManager, ConfigValue
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL,
    resolve_rune_paths,
)
from mvgeos_agent.environment import (
    DEFAULT_GUIDELINES,
    DEFAULT_GUIDELINES_MD,
    DEFAULT_SYSTEM_PROMPT,
    AgentConfig,
    MvgeEnvironment,
    PromptSource,
    ResolvedGuidelines,
    ResolvedPrompt,
    coerce_agent_config,
    ensure_config_files,
    get_environment_info,
    render_prompt,
    resolve_config_dir,
    resolve_guidelines,
    resolve_system_prompt,
)
from mvgeos_agent.mvge import Mvge
from mvgeos_agent.snapshot import RuntimeSnapshot
from mvgeos_agent.types import QueueMode


def _cfg(**kwargs: Any) -> dict[str, ConfigValue]:
    return {k: ConfigValue(v, ConfigLayer.DEFAULTS) for k, v in kwargs.items()}


def _mock_runner(*, suppressed: bool = False, catalog: str = "") -> MagicMock:
    runner = MagicMock(spec=RuneRunner)
    runner.emit_chain = AsyncMock(side_effect=lambda hook, initial: initial)
    runner.is_skill_catalog_suppressed = MagicMock(return_value=suppressed)
    runner.get_skill_catalog = MagicMock(return_value=catalog)
    return runner


# ---------------------------------------------------------------------------
# Types and Enums
# ---------------------------------------------------------------------------


class TestPromptSource:
    def test_values_are_descriptive_strings(self) -> None:
        assert PromptSource.CUSTOM_LITERAL == "custom_literal"
        assert PromptSource.CUSTOM_PATH == "custom_path"
        assert PromptSource.PROJECT_MD == "project_md"
        assert PromptSource.AGENT_MD == "agent_md"
        assert PromptSource.BUILTIN == "builtin"


class TestResolvedDataClasses:
    def test_resolved_prompt_is_frozen(self) -> None:
        resolved = ResolvedPrompt(text="hi", source=PromptSource.BUILTIN)
        with pytest.raises(AttributeError):
            resolved.text = "bye"  # type: ignore[misc]

    def test_resolved_prompt_path_defaults_to_none(self) -> None:
        resolved = ResolvedPrompt(text="hi", source=PromptSource.BUILTIN)
        assert resolved.path is None

    def test_resolved_guidelines_is_frozen(self) -> None:
        resolved = ResolvedGuidelines(guidelines=["a"], source=PromptSource.BUILTIN)
        with pytest.raises(AttributeError):
            resolved.guidelines = ["b"]  # type: ignore[misc]

    def test_resolved_guidelines_path_defaults_to_none(self) -> None:
        resolved = ResolvedGuidelines(guidelines=["a"], source=PromptSource.BUILTIN)
        assert resolved.path is None


# ---------------------------------------------------------------------------
# Config Coercion
# ---------------------------------------------------------------------------


class TestAgentConfigCoercion:
    def test_empty_config_yields_defaults(self) -> None:
        cfg = coerce_agent_config({})
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
        cfg = coerce_agent_config({})
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.temperature = 0.1  # type: ignore[misc]

    def test_int_temperature_coerced_to_float(self) -> None:
        cfg = coerce_agent_config(_cfg(temperature=0))
        assert cfg.temperature == 0.0
        assert isinstance(cfg.temperature, float)

    def test_numeric_string_max_tokens_coerced(self) -> None:
        cfg = coerce_agent_config(_cfg(max_tokens="2048"))
        assert cfg.max_tokens == 2048

    def test_float_max_tokens_coerced(self) -> None:
        cfg = coerce_agent_config(_cfg(max_tokens=8192.0))
        assert cfg.max_tokens == 8192

    def test_string_budget_coerced(self) -> None:
        cfg = coerce_agent_config(_cfg(contemplation_budget="512"))
        assert cfg.contemplation_budget == 512

    def test_truthy_exclude_contemplation(self) -> None:
        cfg = coerce_agent_config(_cfg(exclude_contemplation=1))
        assert cfg.exclude_contemplation is True

    def test_non_string_model_coerced(self) -> None:
        cfg = coerce_agent_config(_cfg(model=12345))
        assert cfg.model_id == "12345"

    def test_queue_mode_string_coerced(self) -> None:
        cfg = coerce_agent_config(_cfg(queue_mode="all"))
        assert cfg.queue_mode is QueueMode.ALL

    def test_queue_mode_enum_passes_through(self) -> None:
        cfg = coerce_agent_config(_cfg(queue_mode=QueueMode.ALL))
        assert cfg.queue_mode is QueueMode.ALL

    def test_boolean_temperature_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(temperature=True))
        assert cfg.temperature == 0.7

    def test_garbage_temperature_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(temperature="invalid"))
        assert cfg.temperature == 0.7

    def test_boolean_max_tokens_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(max_tokens=True))
        assert cfg.max_tokens == 4096

    def test_none_max_tokens_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(max_tokens=None))
        assert cfg.max_tokens == 4096

    def test_unknown_contemplation_level_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(contemplation_level="ultra_high"))
        assert cfg.contemplation_level == "medium"

    def test_list_budget_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(contemplation_budget=[1, 2]))
        assert cfg.contemplation_budget is None

    def test_boolean_budget_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(contemplation_budget=True))
        assert cfg.contemplation_budget is None

    def test_invalid_queue_mode_falls_back(self) -> None:
        cfg = coerce_agent_config(_cfg(queue_mode="bogus"))
        assert cfg.queue_mode is QueueMode.ONE_AT_A_TIME

    def test_spell_names_non_empty_preserved(self) -> None:
        cfg = coerce_agent_config(_cfg(spells_enabled=["bash", "read"]))
        assert cfg.spell_names == ["bash", "read"]

    def test_spell_names_input_list_copied(self) -> None:
        spells = ["bash"]
        cfg = coerce_agent_config(_cfg(spells_enabled=spells))
        spells.append("write")
        assert cfg.spell_names == ["bash"]

    def test_spell_names_empty_normalized_to_none(self) -> None:
        cfg = coerce_agent_config(_cfg(spells_enabled=[]))
        assert cfg.spell_names is None

    def test_spell_names_missing_key_yields_none(self) -> None:
        cfg = coerce_agent_config({})
        assert cfg.spell_names is None

    def test_rune_paths_constructor_wins_over_config(self) -> None:
        cfg = coerce_agent_config(
            _cfg(rune_paths=["/from/config"]),
            runes_paths=["/from/ctor"],
        )
        assert cfg.runes_paths == [Path("/from/ctor")]

    def test_rune_paths_config_used_without_constructor(self) -> None:
        cfg = coerce_agent_config(_cfg(rune_paths=["/from/config"]))
        assert cfg.runes_paths == [Path("/from/config")]

    def test_rune_paths_tilde_expanded(self) -> None:
        cfg = coerce_agent_config(_cfg(rune_paths=["~/runes"]))
        assert cfg.runes_paths == [Path("~/runes").expanduser()]

    def test_rune_paths_default_resolves_agent_name_and_extension_dir(self) -> None:
        cfg = coerce_agent_config({}, agent_name="my-agent", extension_dir="/ext")
        assert cfg.runes_paths == resolve_rune_paths("my-agent", "/ext")


# ---------------------------------------------------------------------------
# Prompt & Guidelines Discovery Chain
# ---------------------------------------------------------------------------


class TestPromptDiscoveryPrecedence:
    def test_custom_literal_wins_over_all(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".agents" / ".mvgeos").mkdir(parents=True)
        (project_dir / ".agents" / ".mvgeos" / "SYSTEM.md").write_text(
            "Project prompt", encoding="utf-8"
        )

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "SYSTEM.md").write_text("Agent prompt", encoding="utf-8")

        resolved = resolve_system_prompt(
            agent_name="test",
            custom="Custom literal",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        assert resolved.text == "Custom literal"
        assert resolved.source == PromptSource.CUSTOM_LITERAL
        assert resolved.path is None

    def test_custom_path_wins_over_project(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".agents" / ".mvgeos").mkdir(parents=True)
        (project_dir / ".agents" / ".mvgeos" / "SYSTEM.md").write_text(
            "Project prompt", encoding="utf-8"
        )

        custom_file = tmp_path / "custom_prompt.txt"
        custom_file.write_text("Custom path prompt", encoding="utf-8")

        resolved = resolve_system_prompt(
            agent_name="test",
            custom=str(custom_file),
            project_dir=project_dir,
        )
        assert resolved.text == "Custom path prompt"
        assert resolved.source == PromptSource.CUSTOM_PATH
        assert resolved.path == custom_file

    def test_project_wins_over_agent(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".agents" / ".mvgeos").mkdir(parents=True)
        (project_dir / ".agents" / ".mvgeos" / "SYSTEM.md").write_text(
            "Project prompt", encoding="utf-8"
        )

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "SYSTEM.md").write_text("Agent prompt", encoding="utf-8")

        resolved = resolve_system_prompt(
            agent_name="test",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        assert resolved.text == "Project prompt"
        assert resolved.source == PromptSource.PROJECT_MD
        assert resolved.path == project_dir / ".agents" / ".mvgeos" / "SYSTEM.md"

    def test_agent_wins_over_builtin(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "SYSTEM.md").write_text("Agent prompt", encoding="utf-8")

        resolved = resolve_system_prompt(
            agent_name="test",
            config_dir=agent_dir,
        )
        assert resolved.text == "Agent prompt"
        assert resolved.source == PromptSource.AGENT_MD
        assert resolved.path == agent_dir / "SYSTEM.md"

    def test_caller_system_prompt_dir(self, tmp_path: Path) -> None:
        caller_dir = tmp_path / "caller_pkg"
        sys_prompt_dir = caller_dir / "system_prompt"
        sys_prompt_dir.mkdir(parents=True)
        (sys_prompt_dir / "SYSTEM.md").write_text(
            "System prompt from subdir", encoding="utf-8"
        )

        resolved = resolve_system_prompt(
            agent_name="test",
            caller_dir=caller_dir,
        )
        assert resolved.text == "System prompt from subdir"
        assert resolved.source == PromptSource.AGENT_MD
        assert resolved.path == sys_prompt_dir / "SYSTEM.md"

    def test_builtin_when_nothing_exists(self, tmp_path: Path) -> None:
        resolved = resolve_system_prompt(
            agent_name="test",
            config_dir=tmp_path / "nonexistent",
        )
        assert resolved.text == DEFAULT_SYSTEM_PROMPT
        assert resolved.source == PromptSource.BUILTIN
        assert resolved.path is None


class TestGuidelinesDiscoveryPrecedence:
    def test_project_wins_over_agent(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".agents" / ".mvgeos").mkdir(parents=True)
        (project_dir / ".agents" / ".mvgeos" / "GUIDELINES.md").write_text(
            "- Project rule\n", encoding="utf-8"
        )

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("- Agent rule\n", encoding="utf-8")

        resolved = resolve_guidelines(
            agent_name="test",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        assert resolved.guidelines == ["Project rule"]
        assert resolved.source == PromptSource.PROJECT_MD

    def test_agent_wins_over_builtin(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("- Agent rule\n", encoding="utf-8")

        resolved = resolve_guidelines(
            agent_name="test",
            config_dir=agent_dir,
        )
        assert resolved.guidelines == ["Agent rule"]
        assert resolved.source == PromptSource.AGENT_MD

    def test_caller_guidelines_system_prompt_dir(self, tmp_path: Path) -> None:
        caller_dir = tmp_path / "caller_pkg"
        sys_prompt_dir = caller_dir / "system_prompt"
        sys_prompt_dir.mkdir(parents=True)
        (sys_prompt_dir / "GUIDELINES.md").write_text(
            "- Subdir rule 1\n- Subdir rule 2\n", encoding="utf-8"
        )

        resolved = resolve_guidelines(
            agent_name="test",
            caller_dir=caller_dir,
        )
        assert resolved.guidelines == ["Subdir rule 1", "Subdir rule 2"]
        assert resolved.source == PromptSource.AGENT_MD
        assert resolved.path == sys_prompt_dir / "GUIDELINES.md"

    def test_builtin_when_nothing_exists(self, tmp_path: Path) -> None:
        resolved = resolve_guidelines(
            agent_name="test",
            config_dir=tmp_path / "nonexistent",
        )
        assert resolved.guidelines == DEFAULT_GUIDELINES
        assert resolved.source == PromptSource.BUILTIN

    def test_empty_agent_guidelines_falls_back_to_builtin(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("   \n", encoding="utf-8")

        resolved = resolve_guidelines(
            agent_name="test",
            config_dir=agent_dir,
        )
        assert resolved.guidelines == DEFAULT_GUIDELINES
        assert resolved.source == PromptSource.BUILTIN

    def test_bullet_markers_are_stripped(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text(
            "- Dash rule\n* Star rule\nBare rule\n", encoding="utf-8"
        )

        resolved = resolve_guidelines(
            agent_name="test",
            config_dir=agent_dir,
        )
        assert resolved.guidelines == ["Dash rule", "Star rule", "Bare rule"]


# ---------------------------------------------------------------------------
# Seeding and Config Directory
# ---------------------------------------------------------------------------


class TestConfigDirAndSeeding:
    def test_resolve_config_dir_defaults_to_dotagents(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        resolved = resolve_config_dir("my-mvge")
        assert resolved == tmp_path / ".agents" / ".mvgeos" / "my-mvge"

    def test_resolve_config_dir_explicit_wins(self, tmp_path: Path) -> None:
        assert resolve_config_dir("my-mvge", tmp_path) == tmp_path

    def test_ensure_config_files_creates_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")
        assert (config_dir / "SYSTEM.md").exists()
        assert (config_dir / "GUIDELINES.md").exists()

        system_text = (config_dir / "SYSTEM.md").read_text(encoding="utf-8")
        assert DEFAULT_SYSTEM_PROMPT in system_text
        guidelines_text = (config_dir / "GUIDELINES.md").read_text(encoding="utf-8")
        assert guidelines_text == DEFAULT_GUIDELINES_MD

    def test_ensure_config_files_never_overwrites(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")
        (config_dir / "GUIDELINES.md").write_text("- Custom rule\n", encoding="utf-8")
        (config_dir / "SYSTEM.md").write_text("Custom prompt", encoding="utf-8")

        ensure_config_files("test-mvge")
        assert (config_dir / "GUIDELINES.md").read_text(
            encoding="utf-8"
        ) == "- Custom rule\n"
        assert (config_dir / "SYSTEM.md").read_text(encoding="utf-8") == "Custom prompt"


# ---------------------------------------------------------------------------
# Template Rendering & Environment Info
# ---------------------------------------------------------------------------


class TestPromptRendering:
    def test_render_prompt_basic(self) -> None:
        rendered = render_prompt(
            body="Base body",
            spells=["bash", "read"],
            guidelines=["Be concise."],
            cwd="/test/dir",
        )
        assert "Base body" in rendered
        assert "Active spells:" in rendered
        assert "  - bash" in rendered
        assert "  - read" in rendered
        assert "Guidelines:" in rendered
        assert "- Be concise." in rendered
        assert "Environment:" in rendered
        assert "Working Directory: /test/dir" in rendered

    def test_render_prompt_no_spells(self) -> None:
        rendered = render_prompt(
            body="Base body",
            spells=[],
            guidelines=[],
        )
        assert "(none)" in rendered
        assert "Guidelines:" not in rendered

    def test_render_prompt_append_text(self) -> None:
        rendered = render_prompt(
            body="Base",
            append_text="Extra footer note",
        )
        assert "Extra footer note" in rendered

    def test_get_environment_info_contains_os_and_shell(self) -> None:
        lines = get_environment_info("/custom/cwd")
        joined = "\n".join(lines)
        assert "Operating System:" in joined
        assert "Shell:" in joined
        assert "Working Directory: /custom/cwd" in joined


# ---------------------------------------------------------------------------
# MvgeEnvironment.resolve & assemble_system_prompt
# ---------------------------------------------------------------------------


class TestMvgeEnvironmentResolve:
    def test_resolve_defaults(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "agent_config"
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=config_dir
        )

        assert env.agent_name == "test-agent"
        assert env.model_id == DEFAULT_MODEL
        assert env.temperature == 0.7
        assert env.max_tokens == 4096
        assert env.contemplation_level == "medium"
        assert env.spell_names == ConfigManager.DEFAULTS["spells_enabled"]
        assert env.resolved_prompt.source == PromptSource.BUILTIN
        assert env.resolved_guidelines.source == PromptSource.BUILTIN
        assert "model" in env.config
        assert env.config["model"].layer == ConfigLayer.DEFAULTS

    def test_resolve_with_overrides(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "agent_config"
        overrides = {
            "model": "google/gemini-2.5-flash",
            "temperature": 0.2,
            "max_tokens": 2048,
            "contemplation_level": "high",
            "queue_mode": "all",
        }
        env = MvgeEnvironment.resolve(
            "test-agent",
            project_dir=tmp_path,
            config_dir=config_dir,
            overrides=overrides,
        )

        assert env.model_id == "google/gemini-2.5-flash"
        assert env.temperature == 0.2
        assert env.max_tokens == 2048
        assert env.contemplation_level == "high"
        assert env.queue_mode is QueueMode.ALL
        assert env.config["model"].layer == ConfigLayer.CONSTRUCTOR

    def test_resolve_project_prompt_and_guidelines(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "agent_config"
        agents_dir = tmp_path / ".agents" / ".mvgeos"
        agents_dir.mkdir(parents=True)
        (agents_dir / "SYSTEM.md").write_text("Custom Project System Prompt")
        (agents_dir / "GUIDELINES.md").write_text("- Guideline 1\n- Guideline 2")

        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=config_dir
        )

        assert env.resolved_prompt.source == PromptSource.PROJECT_MD
        assert env.resolved_prompt.text == "Custom Project System Prompt"
        assert env.resolved_guidelines.source == PromptSource.PROJECT_MD
        assert env.resolved_guidelines.guidelines == ["Guideline 1", "Guideline 2"]

    def test_resolve_is_frozen(self, tmp_path: Path) -> None:
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "agent_config"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.temperature = 0.5  # type: ignore[misc]


class TestMvgeEnvironmentAssemble:
    @pytest.mark.asyncio
    async def test_without_runner_returns_base_prompt(self, tmp_path: Path) -> None:
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )
        assembled = await env.assemble_system_prompt(base_prompt="You are Mvge.")
        assert assembled == "You are Mvge."

    @pytest.mark.asyncio
    async def test_emits_before_mvge_start_once(self, tmp_path: Path) -> None:
        runner = _mock_runner()
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )

        await env.assemble_system_prompt(runner=runner)

        runner.emit_chain.assert_awaited_once()
        call_args = runner.emit_chain.await_args.args
        assert call_args[0] == SigilHook.BEFORE_MVGE_START

    @pytest.mark.asyncio
    async def test_sigil_payload_carries_agent_inputs(self, tmp_path: Path) -> None:
        runner = _mock_runner()
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )

        await env.assemble_system_prompt(
            runner=runner,
            base_prompt="Base prompt.",
            custom_prompt="Custom body",
            spell_names=["bash", "read"],
            cwd="/proj",
            config_dir="/cfg/test-agent",
        )

        payload = runner.emit_chain.await_args.args[1]
        assert payload.base_prompt == "Base prompt."
        assert payload.spell_names == ["bash", "read"]
        assert payload.config_dir == "/cfg/test-agent"
        assert payload.custom_prompt == "Custom body"
        assert payload.agent_name == "test-agent"
        assert payload.cwd == "/proj"

    @pytest.mark.asyncio
    async def test_runner_can_modify_base_prompt(self, tmp_path: Path) -> None:
        async def injector(hook: SigilHook, data: Any) -> Any:
            assert isinstance(data, BeforeMvgeStartData)
            data.base_prompt = "Runes were here."
            return data

        runner = _mock_runner()
        runner.emit_chain = AsyncMock(side_effect=injector)
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )

        result = await env.assemble_system_prompt(runner=runner)
        assert result == "Runes were here."

    @pytest.mark.asyncio
    async def test_skill_catalog_appended(self, tmp_path: Path) -> None:
        runner = _mock_runner(catalog="## Available Skills\n\n### demo")
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )

        result = await env.assemble_system_prompt(runner=runner, base_prompt="Body.")
        assert result == "Body.\n\n## Available Skills\n\n### demo"

    @pytest.mark.asyncio
    async def test_suppressed_catalog_not_appended(self, tmp_path: Path) -> None:
        runner = _mock_runner(suppressed=True, catalog="## Available Skills")
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )

        result = await env.assemble_system_prompt(runner=runner, base_prompt="Body.")
        assert result == "Body."

    @pytest.mark.asyncio
    async def test_empty_catalog_not_appended(self, tmp_path: Path) -> None:
        runner = _mock_runner(catalog="")
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=tmp_path / "cfg"
        )

        result = await env.assemble_system_prompt(runner=runner, base_prompt="Body.")
        assert result == "Body."


# ---------------------------------------------------------------------------
# Snapshots and BaseMvge Parity
# ---------------------------------------------------------------------------


class TestMvgeEnvironmentSnapshot:
    def test_mvge_environment_build_snapshot(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "agent_config"
        env = MvgeEnvironment.resolve(
            "test-agent", project_dir=tmp_path, config_dir=config_dir
        )
        snapshot = env.build_snapshot()

        assert isinstance(snapshot, RuntimeSnapshot)
        assert snapshot.agent_name == "test-agent"
        assert snapshot.model == env.model_id
        assert snapshot.prompt is not None
        assert snapshot.prompt.source == PromptSource.BUILTIN.value

    @pytest.mark.asyncio
    async def test_base_mvge_diagnostics_property_and_zero_load_retention(
        self,
    ) -> None:
        diag = Diagnostic(
            kind=DiagnosticKind.LOAD_FAILURE,
            rune_name="broken_rune",
            message="failed to import module",
            scope=RuneScope.USER,
        )

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], [diag]),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            agent = Mvge(api_key="test-key")
            await agent._load_runes()

            assert len(agent.diagnostics) == 1
            assert agent.diagnostics[0].rune_name == "broken_rune"
            assert agent.environment.diagnostics == agent.diagnostics

    def test_base_mvge_matches_environment_coercion(self, tmp_path: Path) -> None:
        custom_defaults = {
            "model": "parity-model",
            "temperature": "invalid",
            "max_tokens": "2048",
            "contemplation_level": "high",
            "contemplation_budget": "256",
            "exclude_contemplation": True,
            "queue_mode": "all",
            "spells_enabled": ["bash", "read"],
            "rune_paths": [str(tmp_path / "runes")],
        }
        mgr = ConfigManager(
            agent_name="test-agent",
            project_dir=tmp_path,
            defaults=custom_defaults,
            agent_config_base=tmp_path / "agent_configs",
        )
        env = MvgeEnvironment.resolve(
            "test-agent",
            project_dir=tmp_path,
            config_manager=mgr,
        )
        agent = Mvge(api_key="test-key", environment=env)

        assert isinstance(env.agent_config, AgentConfig)
        assert agent._model_id == env.model_id
        assert agent._temperature == env.temperature
        assert agent._max_tokens == env.max_tokens
        assert agent._contemplation_level == env.contemplation_level
        assert agent._contemplation_budget == env.contemplation_budget
        assert agent._exclude_contemplation == env.exclude_contemplation
        assert agent._queue_mode == env.queue_mode
        assert agent._spell_names == env.spell_names
        assert agent._runes_paths == env.runes_paths
