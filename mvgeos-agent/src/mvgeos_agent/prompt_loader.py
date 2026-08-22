from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from mvgeos_agent.constants import DEFAULT_AGENT_NAME

logger = logging.getLogger(__name__)


class PromptSource(StrEnum):
    """Where a resolved prompt resource came from."""

    CUSTOM_LITERAL = auto()
    CUSTOM_PATH = auto()
    PROJECT_MD = auto()
    AGENT_MD = auto()
    BUILTIN = auto()


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


class PromptLoader:
    """Resolves system prompts and guidelines through a discovery chain.

    System prompt chain (highest to lowest precedence):
      custom literal-or-path -> project SYSTEM.md -> agent-scope SYSTEM.md
      -> built-in default

    Guidelines chain (highest to lowest precedence):
      project GUIDELINES.md -> agent-scope GUIDELINES.md -> built-in default

    The ``config_dir`` parameter sets the agent-scope directory
    (``~/.agents/.mvgeos/{name}/`` by default). ``project_dir`` sets the
    base for the project-scope directory (``$project_dir/.agents/.mvgeos/``,
    ``cwd`` by default).
    """

    def __init__(
        self,
        agent_name: str = DEFAULT_AGENT_NAME,
        config_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self._agent_name = agent_name
        self._config_dir = config_dir
        self._project_dir = project_dir

    @property
    def agent_scope_dir(self) -> Path:
        """Agent-scope directory: ``~/.agents/.mvgeos/{name}/``."""
        if self._config_dir is not None:
            return self._config_dir
        return Path(f"~/.agents/.mvgeos/{self._agent_name}").expanduser()

    @property
    def project_scope_dir(self) -> Path:
        """Project-scope directory: ``$project_dir/.agents/.mvgeos/``."""
        base = self._project_dir if self._project_dir is not None else Path.cwd()
        return base / ".agents" / ".mvgeos"

    def resolve_system_prompt(
        self,
        custom: str = "",
        *,
        default: str,
        filename: str = "SYSTEM.md",
    ) -> ResolvedPrompt:
        """Resolve the system prompt from the discovery chain.

        If ``custom`` is a path to an existing file, it is read as a
        custom path. Otherwise it is used as a literal string.
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

        project_file = self.project_scope_dir / filename
        if project_file.is_file():
            text = _read_text(project_file)
            if text:
                return ResolvedPrompt(
                    text=text, source=PromptSource.PROJECT_MD, path=project_file
                )

        agent_file = self.agent_scope_dir / filename
        if agent_file.is_file():
            text = _read_text(agent_file)
            if text:
                return ResolvedPrompt(
                    text=text, source=PromptSource.AGENT_MD, path=agent_file
                )

        return ResolvedPrompt(text=default, source=PromptSource.BUILTIN)

    def resolve_guidelines(
        self,
        *,
        default: list[str],
        filename: str = "GUIDELINES.md",
    ) -> ResolvedGuidelines:
        """Resolve guidelines from the discovery chain."""
        project_file = self.project_scope_dir / filename
        if project_file.is_file():
            parsed = _parse_guidelines(project_file)
            if parsed:
                return ResolvedGuidelines(
                    guidelines=parsed,
                    source=PromptSource.PROJECT_MD,
                    path=project_file,
                )

        agent_file = self.agent_scope_dir / filename
        if agent_file.is_file():
            parsed = _parse_guidelines(agent_file)
            if parsed:
                return ResolvedGuidelines(
                    guidelines=parsed,
                    source=PromptSource.AGENT_MD,
                    path=agent_file,
                )

        return ResolvedGuidelines(guidelines=list(default), source=PromptSource.BUILTIN)


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
