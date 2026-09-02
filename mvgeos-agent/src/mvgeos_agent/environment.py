from __future__ import annotations

import logging
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    BeforeMvgeStartData,
    Diagnostic,
    RuneManifest,
    SigilHook,
    SkillDiagnostic,
    SkillManifest,
    SpellDefinition,
)

from mvgeos_agent.config_manager import (
    ConfigLayer,
    ConfigManager,
    ConfigValue,
    validate_agent_name,
)
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL,
    resolve_rune_paths,
)
from mvgeos_agent.snapshot import RuntimeSnapshot, assemble_snapshot
from mvgeos_agent.types import MvgeSpell, QueueMode
from mvgeos_agent.types import PromptSource as PromptSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedPrompt:
    """A system prompt resolved through the discovery chain.

    The ``source`` and ``path`` expose which layer won for runtime
    introspection.
    """

    text: str
    source: PromptSource
    path: Path | None = None


@dataclass(frozen=True)
class ResolvedGuidelines:
    """Guidelines resolved through the discovery chain.

    The ``source`` and ``path`` expose which layer won for runtime
    introspection.
    """

    guidelines: list[str]
    source: PromptSource
    path: Path | None = None


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


_SYSTEM_PROMPT_BODY = (
    "You are an AI assistant equipped with spells(tools) to assist your "
    "Summoner(user). Be direct, concise, and technical."
)

DEFAULT_SYSTEM_PROMPT = _SYSTEM_PROMPT_BODY

DEFAULT_GUIDELINES: list[str] = []

SYSTEM_MD_FILENAME = "SYSTEM.md"
GUIDELINES_MD_FILENAME = "GUIDELINES.md"

DEFAULT_SYSTEM_MD = _SYSTEM_PROMPT_BODY + "\n"
DEFAULT_GUIDELINES_MD = ""


def get_environment_info(cwd: str | Path | None = None) -> list[str]:
    """Return OS, terminal environment, working directory, and UTC timestamp."""
    os_name = platform.system()
    os_release = platform.release()
    arch = platform.machine()

    lines = [
        f"- Operating System: {os_name} {os_release} ({sys.platform}, {arch})",
    ]

    if sys.platform == "win32":
        lines.append("- Shell: PowerShell (powershell.exe)")
        lines.append(
            "- Shell Syntax: Use PowerShell syntax and cmdlets. Chain commands "
            "with ';' rather than '&&'. Use non-interactive flags (e.g. "
            "'Get-Date' instead of interactive 'date')."
        )
    else:
        shell = os.environ.get("SHELL", "/bin/bash")
        lines.append(f"- Shell: {shell}")

    effective_cwd = str(cwd) if cwd else str(Path.cwd())
    lines.append(f"- Working Directory: {effective_cwd}")

    now_utc = datetime.now(UTC).strftime("%A, %B %d, %Y, %I:%M %p UTC")
    lines.append(f"- Current Date & Time: {now_utc}")

    return lines


def render_prompt(
    body: str,
    spells: Sequence[str] = (),
    guidelines: Sequence[str] = (),
    cwd: str | Path | None = None,
    append_text: str = "",
    *,
    spells_dir: Path | None = None,
    skills_paths: Sequence[Path] = (),
    runes_paths: Sequence[Path] = (),
    system_path: Path | None = None,
    guidelines_path: Path | None = None,
) -> str:
    """The single rendering every entry point goes through."""
    parts: list[str] = []
    if body:
        parts.append(body)

    guidelines_list = list(guidelines)
    if guidelines_list:
        parts.append("\nGuidelines:")
        parts.extend(f"- {guideline}" for guideline in guidelines_list)

    spells_list = list(spells)
    spell_list_str = (
        "\n".join(f"  - {s}" for s in spells_list) if spells_list else "  (none)"
    )
    parts.append(f"\nActive spells:\n{spell_list_str}")

    parts.append("\nEnvironment:")
    parts.extend(get_environment_info(cwd))

    # Self-Modification & Customization section (on-demand AGENTS.md reference pattern)
    effective_cwd_path = Path(cwd) if cwd else Path.cwd()
    project_agents_file = effective_cwd_path / "AGENTS.md"

    self_mod_lines = [
        "\nSelf-Modification & Customization:",
        "You can extend and self-modify your capabilities by editing files with "
        "your spells (changes are watched and hot-reloaded automatically). "
        "Before creating or modifying, read the AGENTS.md in that directory for "
        "exact syntax, rules, and contracts:",
    ]
    has_self_mod = False
    if spells_dir is not None and spells_dir.is_dir():
        self_mod_lines.append(f"- Spells: {spells_dir.as_posix()}/AGENTS.md")
        has_self_mod = True
    if skills_paths:
        for sp in skills_paths:
            self_mod_lines.append(f"- Skills: {sp.as_posix()}/AGENTS.md")
            has_self_mod = True
    if runes_paths:
        for rp in runes_paths:
            self_mod_lines.append(f"- Runes: {rp.as_posix()}/AGENTS.md")
            has_self_mod = True
    if project_agents_file.is_file():
        self_mod_lines.append(f"- Project Rules: {project_agents_file.as_posix()}")
        has_self_mod = True
    if guidelines_path is not None and guidelines_path.is_file():
        self_mod_lines.append(f"- Guidelines: {guidelines_path.as_posix()}")
        has_self_mod = True
    if system_path is not None and system_path.is_file():
        self_mod_lines.append(f"- System Instructions: {system_path.as_posix()}")
        has_self_mod = True

    if has_self_mod:
        parts.extend(self_mod_lines)

    # Workspace AGENTS.md context injection
    if project_agents_file.is_file():
        content = _read_text(project_agents_file)
        if content:
            proj_instr = (
                f'<project_instructions path="AGENTS.md">\n'
                f"{content}\n"
                f"</project_instructions>\n"
            )
            parts.append(
                "\n<project_context>\n"
                "Project-specific instructions and guidelines:\n\n"
                f"{proj_instr}</project_context>"
            )

    if append_text:
        parts.append(f"\n{append_text}")

    return "\n".join(parts)


def resolve_config_dir(name: str, config_dir: Path | None = None) -> Path:
    """The one place a Mvge's configuration lives.

    Defaults to the dotagents path `~/.agents/.mvgeos/{name}/`. An explicit
    directory overrides it, which is what tests and embedders pass.
    """
    if config_dir is not None:
        return config_dir
    return Path(f"~/.agents/.mvgeos/{name}").expanduser()


def ensure_config_files(name: str, config_dir: Path | None = None) -> Path:
    """Create SYSTEM.md and GUIDELINES.md with editable defaults if absent.

    Both files are the Summoner's configuration surface, so they are seeded
    with real content rather than left empty. Existing files are never
    overwritten.
    """
    resolved = resolve_config_dir(name, config_dir)
    resolved.mkdir(parents=True, exist_ok=True)

    for filename, content in (
        (SYSTEM_MD_FILENAME, DEFAULT_SYSTEM_MD),
        (GUIDELINES_MD_FILENAME, DEFAULT_GUIDELINES_MD),
    ):
        path = resolved / filename
        # An empty file counts as unseeded: earlier versions created
        # GUIDELINES.md with touch(), leaving nothing to edit.
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            path.write_text(content, encoding="utf-8")

    return resolved


def _read_text(path: Path) -> str:
    """Read a file's text, stripped, returning empty on error."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Could not read file at %s", path)
        return ""


def _parse_guidelines(path: Path) -> list[str]:
    """Read a guidelines file into bare lines, dropping bullet markers."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read guidelines at %s", path)
        return []
    return [
        stripped.lstrip("-*").strip()
        for line in raw.splitlines()
        if (stripped := line.strip())
    ]


def resolve_system_prompt(
    agent_name: str = DEFAULT_AGENT_NAME,
    *,
    custom: str = "",
    config_dir: Path | None = None,
    project_dir: Path | None = None,
    caller_dir: Path | None = None,
    default: str = DEFAULT_SYSTEM_PROMPT,
    filename: str = SYSTEM_MD_FILENAME,
) -> ResolvedPrompt:
    """Resolve the system prompt from the discovery chain:
    custom -> caller SYSTEM.md -> project SYSTEM.md -> agent-scope SYSTEM.md -> default
    """
    if custom:
        custom_path = Path(custom).expanduser()
        if custom_path.is_file():
            return ResolvedPrompt(
                text=_read_text(custom_path),
                source=PromptSource.CUSTOM_PATH,
                path=custom_path,
            )
        return ResolvedPrompt(text=custom, source=PromptSource.CUSTOM_LITERAL)

    if caller_dir is not None:
        caller_sys_dir = caller_dir / "system_prompt" / filename
        if caller_sys_dir.is_file():
            text = _read_text(caller_sys_dir)
            if text:
                return ResolvedPrompt(
                    text=text, source=PromptSource.AGENT_MD, path=caller_sys_dir
                )
        caller_file = caller_dir / filename
        if caller_file.is_file():
            text = _read_text(caller_file)
            if text:
                return ResolvedPrompt(
                    text=text, source=PromptSource.AGENT_MD, path=caller_file
                )

    proj_base = project_dir if project_dir is not None else Path.cwd()
    project_file = proj_base / ".agents" / ".mvgeos" / filename
    if project_file.is_file():
        text = _read_text(project_file)
        if text:
            return ResolvedPrompt(
                text=text, source=PromptSource.PROJECT_MD, path=project_file
            )

    agent_dir = resolve_config_dir(agent_name, config_dir)
    agent_file = agent_dir / filename
    if agent_file.is_file():
        text = _read_text(agent_file)
        if text:
            return ResolvedPrompt(
                text=text, source=PromptSource.AGENT_MD, path=agent_file
            )

    return ResolvedPrompt(text=default, source=PromptSource.BUILTIN)


def resolve_guidelines(
    agent_name: str = DEFAULT_AGENT_NAME,
    *,
    config_dir: Path | None = None,
    project_dir: Path | None = None,
    caller_dir: Path | None = None,
    default: Sequence[str] = DEFAULT_GUIDELINES,
    filename: str = GUIDELINES_MD_FILENAME,
) -> ResolvedGuidelines:
    """Resolve guidelines from the discovery chain:
    caller system_prompt/GUIDELINES.md -> project GUIDELINES.md ->
    agent-scope GUIDELINES.md -> default.
    """
    if caller_dir is not None:
        caller_sys_dir = caller_dir / "system_prompt" / filename
        if caller_sys_dir.is_file():
            parsed = _parse_guidelines(caller_sys_dir)
            if parsed:
                return ResolvedGuidelines(
                    guidelines=parsed,
                    source=PromptSource.AGENT_MD,
                    path=caller_sys_dir,
                )
        caller_file = caller_dir / filename
        if caller_file.is_file():
            parsed = _parse_guidelines(caller_file)
            if parsed:
                return ResolvedGuidelines(
                    guidelines=parsed,
                    source=PromptSource.AGENT_MD,
                    path=caller_file,
                )

    proj_base = project_dir if project_dir is not None else Path.cwd()
    project_file = proj_base / ".agents" / ".mvgeos" / filename
    if project_file.is_file():
        parsed = _parse_guidelines(project_file)
        if parsed:
            return ResolvedGuidelines(
                guidelines=parsed,
                source=PromptSource.PROJECT_MD,
                path=project_file,
            )

    agent_dir = resolve_config_dir(agent_name, config_dir)
    agent_file = agent_dir / filename
    if agent_file.is_file():
        parsed = _parse_guidelines(agent_file)
        if parsed:
            return ResolvedGuidelines(
                guidelines=parsed,
                source=PromptSource.AGENT_MD,
                path=agent_file,
            )

    return ResolvedGuidelines(guidelines=list(default), source=PromptSource.BUILTIN)


def coerce_agent_config(
    config: Mapping[str, ConfigValue],
    *,
    agent_name: str = DEFAULT_AGENT_NAME,
    extension_dir: str | None = None,
    runes_paths: Sequence[str] | None = None,
) -> AgentConfig:
    """Coerces raw resolved config mapping into a validated AgentConfig."""

    def _get(key: str, default: Any) -> Any:
        return config.get(key, ConfigValue(default, ConfigLayer.DEFAULTS)).value

    # Model
    model_id = str(_get("model", DEFAULT_MODEL))

    # Temperature
    raw_temp = _get("temperature", 0.7)
    try:
        if isinstance(raw_temp, bool):
            raise TypeError("temperature cannot be boolean")
        temperature = float(raw_temp)
    except ValueError, TypeError:
        logger.warning(
            "Invalid temperature in config (%r); falling back to default %s",
            raw_temp,
            0.7,
        )
        temperature = 0.7

    # Max tokens
    raw_max_tokens = _get("max_tokens", 4096)
    try:
        if isinstance(raw_max_tokens, bool):
            raise TypeError("max_tokens cannot be boolean")
        max_tokens = int(raw_max_tokens)
    except ValueError, TypeError:
        logger.warning(
            "Invalid max_tokens in config (%r); falling back to default %s",
            raw_max_tokens,
            4096,
        )
        max_tokens = 4096

    # Contemplation level
    raw_level = str(_get("contemplation_level", "medium"))
    if raw_level in _VALID_CONTEMPLATION_LEVELS:
        contemplation_level = raw_level
    else:
        logger.warning(
            "Invalid contemplation_level in config (%r); "
            "falling back to default 'medium'",
            raw_level,
        )
        contemplation_level = "medium"

    # Contemplation budget
    raw_budget = _get("contemplation_budget", None)
    if raw_budget is None:
        contemplation_budget = None
    else:
        try:
            if isinstance(raw_budget, bool):
                raise TypeError("contemplation_budget cannot be boolean")
            contemplation_budget = int(raw_budget)
        except ValueError, TypeError:
            logger.warning(
                "Invalid contemplation_budget in config (%r); "
                "falling back to default None",
                raw_budget,
            )
            contemplation_budget = None

    # Exclude contemplation
    exclude_contemplation = bool(_get("exclude_contemplation", False))

    # Queue mode
    raw_queue = _get("queue_mode", QueueMode.ONE_AT_A_TIME)
    if isinstance(raw_queue, QueueMode):
        queue_mode = raw_queue
    else:
        try:
            queue_mode = QueueMode(str(raw_queue))
        except ValueError:
            logger.warning(
                "Invalid queue_mode in config (%r); "
                "falling back to default 'one-at-a-time'",
                raw_queue,
            )
            queue_mode = QueueMode.ONE_AT_A_TIME

    # Spells enabled
    spells_enabled = _get("spells_enabled", [])
    spell_names = list(spells_enabled) if spells_enabled else None

    # Rune paths
    if runes_paths is not None:
        coerced_runes_paths = [Path(str(p)).expanduser() for p in runes_paths]
    else:
        rune_paths_config = _get("rune_paths", None)
        if rune_paths_config:
            coerced_runes_paths = [Path(str(p)).expanduser() for p in rune_paths_config]
        else:
            coerced_runes_paths = resolve_rune_paths(agent_name, extension_dir)

    return AgentConfig(
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        contemplation_level=contemplation_level,
        contemplation_budget=contemplation_budget,
        exclude_contemplation=exclude_contemplation,
        queue_mode=queue_mode,
        spell_names=spell_names,
        runes_paths=coerced_runes_paths,
    )


@dataclass(frozen=True)
class MvgeEnvironment:
    """Consolidated agent environment holding resolved configuration and resources.

    Achieves 1-to-1 parity with Pi's ``AgentSessionServices`` + ``ResourceLoader``.
    """

    agent_name: str
    model_id: str
    temperature: float
    max_tokens: int
    contemplation_level: str
    contemplation_budget: int | None
    exclude_contemplation: bool
    queue_mode: QueueMode
    spell_names: list[str] | None
    runes_paths: list[Path]
    config: dict[str, ConfigValue]
    resolved_prompt: ResolvedPrompt
    resolved_guidelines: ResolvedGuidelines
    diagnostics: list[Diagnostic | SkillDiagnostic] = field(default_factory=list)
    spells: list[MvgeSpell | SpellDefinition] = field(default_factory=list)
    runner: RuneRunner | None = None
    config_manager: ConfigManager | None = None
    agent_config: AgentConfig | None = None

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
        allow_unknown_agent: bool = False,
        caller_dir: Path | None = None,
        extension_dir: str | None = None,
        runes_paths: Sequence[str] | None = None,
    ) -> MvgeEnvironment:
        """Resolve all environment resources and configuration layers."""
        validate_agent_name(
            agent_name,
            agent_config_base=config_dir.parent if config_dir is not None else None,
            project_dir=project_dir,
            allow_create=allow_unknown_agent or (config_dir is not None),
        )
        cm = config_manager or ConfigManager(
            agent_name=agent_name,
            project_dir=project_dir,
            agent_config_base=config_dir.parent if config_dir is not None else None,
        )
        if overrides:
            cm = cm.with_overrides(**overrides)
        resolved_config = cm.load()

        coerced = coerce_agent_config(
            resolved_config,
            agent_name=agent_name,
            extension_dir=extension_dir,
            runes_paths=runes_paths,
        )

        resolved_prompt = resolve_system_prompt(
            agent_name=agent_name,
            custom=custom_prompt,
            config_dir=config_dir,
            project_dir=project_dir,
            caller_dir=caller_dir,
            default=DEFAULT_SYSTEM_PROMPT,
        )
        resolved_guidelines = resolve_guidelines(
            agent_name=agent_name,
            config_dir=config_dir,
            project_dir=project_dir,
            caller_dir=caller_dir,
            default=DEFAULT_GUIDELINES,
        )

        diags: list[Diagnostic | SkillDiagnostic] = []
        if runner is not None:
            diags.extend(runner.diagnostics)
            diags.extend(runner.skill_diagnostics)

        return cls(
            agent_name=agent_name,
            model_id=coerced.model_id,
            temperature=coerced.temperature,
            max_tokens=coerced.max_tokens,
            contemplation_level=coerced.contemplation_level,
            contemplation_budget=coerced.contemplation_budget,
            exclude_contemplation=coerced.exclude_contemplation,
            queue_mode=coerced.queue_mode,
            spell_names=coerced.spell_names,
            runes_paths=coerced.runes_paths,
            config=resolved_config,
            resolved_prompt=resolved_prompt,
            resolved_guidelines=resolved_guidelines,
            diagnostics=diags,
            spells=spells or [],
            runner=runner,
            config_manager=cm if has_config_manager else None,
            agent_config=coerced,
        )

    async def assemble_system_prompt(
        self,
        runner: RuneRunner | None = None,
        *,
        base_prompt: str | None = None,
        custom_prompt: str = "",
        cwd: str | Path | None = None,
        spell_names: Sequence[str] | None = None,
        config_dir: str | Path | None = None,
    ) -> str:
        """Asynchronously assemble the final system prompt string.

        With a runner, emits ``BEFORE_MVGE_START`` so runes can rewrite the
        base prompt, then appends the skill catalog unless a rune suppressed it.
        Without a runner, the base prompt passes through unchanged.
        """
        effective_runner = runner if runner is not None else self.runner
        effective_base = (
            base_prompt if base_prompt is not None else self.resolved_prompt.text
        )
        effective_cwd = str(cwd) if cwd else str(Path.cwd())
        effective_spells = (
            list(spell_names)
            if spell_names is not None
            else (list(self.spell_names) if self.spell_names else [])
        )
        effective_config_dir = (
            str(config_dir)
            if config_dir is not None
            else str(resolve_config_dir(self.agent_name))
        )

        if effective_runner is not None:
            prompt_data = BeforeMvgeStartData(
                base_prompt=effective_base,
                spell_names=effective_spells,
                config_dir=effective_config_dir,
                custom_prompt=custom_prompt,
                agent_name=self.agent_name,
                cwd=effective_cwd,
            )
            result_data = await effective_runner.emit_chain(
                SigilHook.BEFORE_MVGE_START, prompt_data
            )
            if isinstance(result_data, BeforeMvgeStartData):
                effective_base = result_data.base_prompt
            elif isinstance(result_data, dict):
                effective_base = str(result_data.get("base_prompt", effective_base))
            elif hasattr(result_data, "base_prompt"):
                effective_base = str(result_data.base_prompt)

            if not effective_runner.is_skill_catalog_suppressed():
                skill_catalog = effective_runner.get_skill_catalog()
                if skill_catalog:
                    effective_base = f"{effective_base}\n\n{skill_catalog}"

        return effective_base

    @staticmethod
    def render_prompt(
        body: str,
        spells: Sequence[str] = (),
        guidelines: Sequence[str] = (),
        cwd: str | Path | None = None,
        append_text: str = "",
        *,
        spells_dir: Path | None = None,
        skills_paths: Sequence[Path] = (),
        runes_paths: Sequence[Path] = (),
        system_path: Path | None = None,
        guidelines_path: Path | None = None,
    ) -> str:
        """Render a prompt with body, spells, guidelines, and environment."""
        return render_prompt(
            body=body,
            spells=spells,
            guidelines=guidelines,
            cwd=cwd,
            append_text=append_text,
            spells_dir=spells_dir,
            skills_paths=skills_paths,
            runes_paths=runes_paths,
            system_path=system_path,
            guidelines_path=guidelines_path,
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
