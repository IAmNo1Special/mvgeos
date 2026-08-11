from __future__ import annotations

from pathlib import Path

from mvgeos_agent.config_manager import ConfigLayer
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.prompt_loader import PromptSource
from mvgeos_agent.snapshot import RuntimeSnapshot


def test_mvge_environment_resolve_defaults(tmp_path: Path) -> None:
    config_dir = tmp_path / "agent_config"
    env = MvgeEnvironment.resolve(
        "test-agent", project_dir=tmp_path, config_dir=config_dir
    )

    assert env.agent_name == "test-agent"
    assert env.model_id == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert env.resolved_prompt.source == PromptSource.BUILTIN
    assert env.resolved_guidelines.source == PromptSource.BUILTIN
    assert "model" in env.config
    assert env.config["model"].layer == ConfigLayer.DEFAULTS


def test_mvge_environment_resolve_with_overrides(tmp_path: Path) -> None:
    config_dir = tmp_path / "agent_config"
    overrides = {
        "model": "google/gemini-2.5-flash",
        "temperature": 0.2,
        "max_tokens": 2048,
    }
    env = MvgeEnvironment.resolve(
        "test-agent", project_dir=tmp_path, config_dir=config_dir, overrides=overrides
    )

    assert env.model_id == "google/gemini-2.5-flash"
    assert env.config["model"].value == "google/gemini-2.5-flash"
    assert env.config["model"].layer == ConfigLayer.CONSTRUCTOR
    assert env.config["temperature"].value == 0.2
    assert env.config["max_tokens"].value == 2048


def test_mvge_environment_resolve_project_prompt_and_guidelines(
    tmp_path: Path,
) -> None:
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


def test_mvge_environment_build_snapshot(tmp_path: Path) -> None:
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
