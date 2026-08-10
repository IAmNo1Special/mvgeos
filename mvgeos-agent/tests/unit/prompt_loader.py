from __future__ import annotations

from pathlib import Path

import pytest

from mvgeos_agent.prompt_loader import (
    PromptLoader,
    PromptSource,
    ResolvedGuidelines,
    ResolvedPrompt,
)


class TestPromptSource:
    def test_values_are_descriptive_strings(self) -> None:
        assert PromptSource.CUSTOM_LITERAL == "custom_literal"
        assert PromptSource.CUSTOM_PATH == "custom_path"
        assert PromptSource.PROJECT_MD == "project_md"
        assert PromptSource.AGENT_MD == "agent_md"
        assert PromptSource.BUILTIN == "builtin"


class TestResolvedPrompt:
    def test_is_frozen_dataclass(self) -> None:
        resolved = ResolvedPrompt(text="hi", source=PromptSource.BUILTIN)
        with pytest.raises(AttributeError):
            resolved.text = "bye"  # type: ignore[misc]

    def test_path_defaults_to_none(self) -> None:
        resolved = ResolvedPrompt(text="hi", source=PromptSource.BUILTIN)
        assert resolved.path is None


class TestResolvedGuidelines:
    def test_is_frozen_dataclass(self) -> None:
        resolved = ResolvedGuidelines(guidelines=["a"], source=PromptSource.BUILTIN)
        with pytest.raises(AttributeError):
            resolved.guidelines = ["b"]  # type: ignore[misc]

    def test_path_defaults_to_none(self) -> None:
        resolved = ResolvedGuidelines(guidelines=["a"], source=PromptSource.BUILTIN)
        assert resolved.path is None


class TestResolveSystemPromptPrecedence:
    """Discovery chain: custom > project > agent > builtin."""

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

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        resolved = loader.resolve_system_prompt(
            custom="Custom literal", default="Built-in"
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

        loader = PromptLoader(
            agent_name="test",
            project_dir=project_dir,
        )
        resolved = loader.resolve_system_prompt(
            custom=str(custom_file), default="Built-in"
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

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        resolved = loader.resolve_system_prompt(default="Built-in")
        assert resolved.text == "Project prompt"
        assert resolved.source == PromptSource.PROJECT_MD
        assert resolved.path == project_dir / ".agents" / ".mvgeos" / "SYSTEM.md"

    def test_agent_wins_over_builtin(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "SYSTEM.md").write_text("Agent prompt", encoding="utf-8")

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
        )
        resolved = loader.resolve_system_prompt(default="Built-in")
        assert resolved.text == "Agent prompt"
        assert resolved.source == PromptSource.AGENT_MD
        assert resolved.path == agent_dir / "SYSTEM.md"

    def test_builtin_when_nothing_exists(self, tmp_path: Path) -> None:
        loader = PromptLoader(
            agent_name="test",
            config_dir=tmp_path / "nonexistent",
        )
        resolved = loader.resolve_system_prompt(default="Built-in default")
        assert resolved.text == "Built-in default"
        assert resolved.source == PromptSource.BUILTIN
        assert resolved.path is None

    def test_custom_literal_takes_precedence_over_custom_path_check(
        self, tmp_path: Path
    ) -> None:
        """A non-existent path string is treated as a literal, not an error."""
        loader = PromptLoader(
            agent_name="test",
            config_dir=tmp_path / "nonexistent",
        )
        resolved = loader.resolve_system_prompt(custom="Not a path", default="Built-in")
        assert resolved.text == "Not a path"
        assert resolved.source == PromptSource.CUSTOM_LITERAL


class TestResolveGuidelinesPrecedence:
    """Discovery chain: project > agent > builtin."""

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

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        resolved = loader.resolve_guidelines(default=["Default rule"])
        assert resolved.guidelines == ["Project rule"]
        assert resolved.source == PromptSource.PROJECT_MD

    def test_agent_wins_over_builtin(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("- Agent rule\n", encoding="utf-8")

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
        )
        resolved = loader.resolve_guidelines(default=["Default rule"])
        assert resolved.guidelines == ["Agent rule"]
        assert resolved.source == PromptSource.AGENT_MD

    def test_builtin_when_nothing_exists(self, tmp_path: Path) -> None:
        loader = PromptLoader(
            agent_name="test",
            config_dir=tmp_path / "nonexistent",
        )
        resolved = loader.resolve_guidelines(default=["Default rule"])
        assert resolved.guidelines == ["Default rule"]
        assert resolved.source == PromptSource.BUILTIN

    def test_empty_agent_guidelines_falls_back_to_builtin(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("   \n", encoding="utf-8")

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
        )
        resolved = loader.resolve_guidelines(default=["Default rule"])
        assert resolved.guidelines == ["Default rule"]
        assert resolved.source == PromptSource.BUILTIN

    def test_empty_project_guidelines_falls_back_to_agent(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".agents" / ".mvgeos").mkdir(parents=True)
        (project_dir / ".agents" / ".mvgeos" / "GUIDELINES.md").write_text(
            "  \n", encoding="utf-8"
        )

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("- Agent rule\n", encoding="utf-8")

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
            project_dir=project_dir,
        )
        resolved = loader.resolve_guidelines(default=["Default rule"])
        assert resolved.guidelines == ["Agent rule"]
        assert resolved.source == PromptSource.AGENT_MD

    def test_bullet_markers_are_stripped(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text(
            "- Dash rule\n* Star rule\nBare rule\n", encoding="utf-8"
        )

        loader = PromptLoader(
            agent_name="test",
            config_dir=agent_dir,
        )
        resolved = loader.resolve_guidelines(default=["Default"])
        assert resolved.guidelines == ["Dash rule", "Star rule", "Bare rule"]


class TestLoaderPathResolution:
    def test_agent_scope_dir_uses_config_dir(self, tmp_path: Path) -> None:
        loader = PromptLoader(agent_name="test", config_dir=tmp_path)
        assert loader.agent_scope_dir == tmp_path

    def test_agent_scope_dir_defaults_to_dotagents(self) -> None:
        loader = PromptLoader(agent_name="my-agent")
        expected = Path.home() / ".agents" / ".mvgeos" / "my-agent"
        assert loader.agent_scope_dir == expected

    def test_project_scope_dir_uses_project_dir(self, tmp_path: Path) -> None:
        loader = PromptLoader(agent_name="test", project_dir=tmp_path)
        assert loader.project_scope_dir == tmp_path / ".agents" / ".mvgeos"

    def test_project_scope_dir_defaults_to_cwd(self) -> None:
        loader = PromptLoader(agent_name="test")
        assert loader.project_scope_dir == Path.cwd() / ".agents" / ".mvgeos"


class TestSourceIntrospection:
    """The resolved source is exposed for runtime introspection."""

    def test_resolved_prompt_reports_source(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "SYSTEM.md").write_text("Agent prompt", encoding="utf-8")

        loader = PromptLoader(agent_name="test", config_dir=agent_dir)
        resolved = loader.resolve_system_prompt(default="Built-in")

        assert resolved.source == PromptSource.AGENT_MD
        assert resolved.path == agent_dir / "SYSTEM.md"

    def test_resolved_guidelines_reports_source(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "GUIDELINES.md").write_text("- Rule\n", encoding="utf-8")

        loader = PromptLoader(agent_name="test", config_dir=agent_dir)
        resolved = loader.resolve_guidelines(default=["Default"])

        assert resolved.source == PromptSource.AGENT_MD
        assert resolved.path == agent_dir / "GUIDELINES.md"

    def test_builtin_source_has_no_path(self, tmp_path: Path) -> None:
        loader = PromptLoader(
            agent_name="test",
            config_dir=tmp_path / "nonexistent",
        )
        resolved_prompt = loader.resolve_system_prompt(default="Built-in")
        assert resolved_prompt.source == PromptSource.BUILTIN
        assert resolved_prompt.path is None

        resolved_guidelines = loader.resolve_guidelines(default=["Default"])
        assert resolved_guidelines.source == PromptSource.BUILTIN
        assert resolved_guidelines.path is None
