from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Diagnostic,
    RuneManifest,
    SkillDiagnostic,
    SkillManifest,
    SpellDefinition,
)

from mvgeos_agent.config_manager import ConfigLayer, ConfigManager, ConfigValue
from mvgeos_agent.constants import DEFAULT_AGENT_NAME, DEFAULT_MODEL
from mvgeos_agent.prompt_config import DEFAULT_GUIDELINES, DEFAULT_SYSTEM_PROMPT
from mvgeos_agent.prompt_loader import (
    PromptLoader,
    ResolvedGuidelines,
    ResolvedPrompt,
)
from mvgeos_agent.snapshot import RuntimeSnapshot, assemble_snapshot
from mvgeos_agent.types import MvgeSpell


@dataclass(frozen=True)
class MvgeEnvironment:
    """Consolidated agent environment holding resolved configuration and resources.

    Achieves 1-to-1 parity with Pi's ``AgentSessionServices`` + ``ResourceLoader``.
    """

    agent_name: str
    model_id: str
    config: dict[str, ConfigValue]
    resolved_prompt: ResolvedPrompt
    resolved_guidelines: ResolvedGuidelines
    diagnostics: list[Diagnostic | SkillDiagnostic] = field(default_factory=list)
    spells: list[MvgeSpell | SpellDefinition] = field(default_factory=list)
    runner: RuneRunner | None = None
    config_manager: ConfigManager | None = None

    @classmethod
    def resolve(
        cls,
        agent_name: str = DEFAULT_AGENT_NAME,
        *,
        project_dir: Path | None = None,
        config_dir: Path | None = None,
        overrides: dict[str, Any] | None = None,
        custom_prompt: str = "",
        spells: list[MvgeSpell | SpellDefinition] | None = None,
        runner: RuneRunner | None = None,
        config_manager: ConfigManager | None = None,
        has_config_manager: bool = True,
    ) -> MvgeEnvironment:
        """Resolve all environment resources and configuration layers."""
        cm = config_manager or ConfigManager(
            agent_name=agent_name,
            project_dir=project_dir,
            agent_config_base=config_dir.parent if config_dir is not None else None,
        )
        if overrides:
            cm = cm.with_overrides(**overrides)
        resolved_config = cm.load()

        model_val = resolved_config.get(
            "model", ConfigValue(DEFAULT_MODEL, ConfigLayer.DEFAULTS)
        )
        model_id = str(model_val.value)

        loader = PromptLoader(
            agent_name=agent_name,
            config_dir=config_dir,
            project_dir=project_dir,
        )
        resolved_prompt = loader.resolve_system_prompt(
            custom=custom_prompt,
            default=DEFAULT_SYSTEM_PROMPT,
        )
        resolved_guidelines = loader.resolve_guidelines(
            default=DEFAULT_GUIDELINES,
        )

        diags: list[Diagnostic | SkillDiagnostic] = []
        if runner is not None:
            diags.extend(runner.diagnostics)
            diags.extend(runner.skill_diagnostics)

        return cls(
            agent_name=agent_name,
            model_id=model_id,
            config=resolved_config,
            resolved_prompt=resolved_prompt,
            resolved_guidelines=resolved_guidelines,
            diagnostics=diags,
            spells=spells or [],
            runner=runner,
            config_manager=cm if has_config_manager else None,
        )

    def build_snapshot(self) -> RuntimeSnapshot:
        """Assemble a resolved runtime snapshot for introspection."""
        rune_manifests: list[RuneManifest] = (
            self.runner.loaded_manifests if self.runner is not None else []
        )
        skills: list[SkillManifest] = (
            self.runner.get_skills() if self.runner is not None else []
        )
        rune_diagnostics: list[Diagnostic] = (
            self.runner.diagnostics if self.runner is not None else []
        )
        skill_diagnostics: list[SkillDiagnostic] = (
            self.runner.skill_diagnostics if self.runner is not None else []
        )

        config_source_files: dict[ConfigLayer, Path | None] = {}
        if self.config_manager is not None:
            config_source_files = {
                ConfigLayer.AGENT: self.config_manager.agent_config_path,
                ConfigLayer.LEGACY: self.config_manager.legacy_config_path,
            }

        return assemble_snapshot(
            agent_name=self.agent_name,
            model=self.model_id,
            spells=self.spells,
            rune_manifests=rune_manifests,
            config_values=self.config if self.config_manager is not None else {},
            config_source_files=config_source_files,
            resolved_prompt=self.resolved_prompt,
            resolved_guidelines=self.resolved_guidelines,
            skills=skills,
            rune_diagnostics=rune_diagnostics,
            skill_diagnostics=skill_diagnostics,
        )
