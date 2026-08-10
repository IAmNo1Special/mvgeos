from __future__ import annotations

import logging
from pathlib import Path

from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_BODY = (
    "You are Mvge, a concise AI coding agent. "
    "You have access to spells (tools) to read files, write code, "
    "edit files, run shell commands, search code, and navigate the filesystem."
)

DEFAULT_SYSTEM_PROMPT = _SYSTEM_PROMPT_BODY

DEFAULT_GUIDELINES = [
    "Be concise. Give short answers unless asked for detail.",
    "Do not speculate or predict the future. "
    "If you don't know something or lack a capability, say so in one "
    "sentence and suggest how you could be equipped to help "
    "(e.g. a web search tool, a new spell, a skill, etc.).",
    "Do not add fluff, filler, or cheerful commentary.",
    "Show file paths when working with files.",
    "When executing shell commands, explain what they do briefly.",
    "Use spells when you need filesystem or command access.",
    "If the user asks a coding question, write working code.",
    "If the user asks a non-coding question, answer briefly or suggest "
    "how you could be equipped to help.",
]

SYSTEM_MD_FILENAME = "SYSTEM.md"
GUIDELINES_MD_FILENAME = "GUIDELINES.md"

# Seed content written when a Summoner has no config yet. Both files are meant
# to be edited: they are the configuration surface, not internal defaults.
DEFAULT_SYSTEM_MD = _SYSTEM_PROMPT_BODY + "\n"

DEFAULT_GUIDELINES_MD = (
    "\n".join(f"- {guideline}" for guideline in DEFAULT_GUIDELINES) + "\n"
)


def resolve_config_dir(name: str, config_dir: Path | None = None) -> Path:
    """The one place a Mvge's configuration lives.

    Defaults to the dotagents path `~/.agents/.mvgeos/{name}/`. An explicit
    directory overrides it, which is what tests and embedders pass.
    """
    if config_dir is not None:
        return config_dir
    return Path(f"~/.agents/.mvgeos/{name}").expanduser()


def _render_prompt(
    body: str,
    spells: list[str],
    guidelines: list[str],
    cwd: str = "",
    append_text: str = "",
) -> str:
    """The single rendering every entry point goes through."""
    parts = [body]

    spell_list = "\n".join(f"  - {s}" for s in spells) if spells else "  (none)"
    parts.append(f"\nActive spells:\n{spell_list}")

    if guidelines:
        parts.append("\nGuidelines:")
        parts.extend(f"- {guideline}" for guideline in guidelines)

    if cwd:
        parts.append(f"\nCurrent working directory: {cwd}")

    return "\n".join(parts)


def build_system_prompt(
    spells: list[str],
    config_dir: Path | None = None,
    cwd: str = "",
    custom_prompt: str = "",
    custom: str = "",
    append_text: str = "",
    context_files: list[dict[str, str]] | None = None,
    name: str = DEFAULT_AGENT_NAME,
) -> str:
    """Build a system prompt with spells, guidelines, and optional context files.

    An explicitly supplied prompt always wins over the Summoner's SYSTEM.md,
    which in turn wins over the built-in default.
    """
    loader = PromptLoader(
        agent_name=name, config_dir=resolve_config_dir(name, config_dir)
    )
    resolved = loader.resolve_system_prompt(
        custom=custom_prompt or custom, default=_SYSTEM_PROMPT_BODY
    )
    guidelines = loader.resolve_guidelines(default=DEFAULT_GUIDELINES)

    return _render_prompt(
        body=resolved.text,
        spells=spells,
        guidelines=guidelines.guidelines,
        cwd=cwd,
        append_text=append_text,
    )


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


def load_system_prompt(
    name: str,
    custom: str = "",
    config_dir: Path | None = None,
    spells: list[str] | None = None,
) -> str:
    """Load the system prompt for a Mvge, falling back to the defaults.

    Shares one config path and one rendering with `build_system_prompt`. An
    explicitly supplied prompt wins over the Summoner's SYSTEM.md.
    """
    resolved_dir = resolve_config_dir(name, config_dir)
    loader = PromptLoader(agent_name=name, config_dir=resolved_dir)
    resolved = loader.resolve_system_prompt(
        custom=custom, default=DEFAULT_SYSTEM_PROMPT
    )
    guidelines = loader.resolve_guidelines(default=DEFAULT_GUIDELINES)

    return _render_prompt(
        body=resolved.text,
        spells=spells or [],
        guidelines=guidelines.guidelines,
    )


def load_guidelines(name: str, config_dir: Path | None = None) -> list[str]:
    """Load guidelines from the config directory, falling back to defaults."""
    resolved_dir = resolve_config_dir(name, config_dir)
    loader = PromptLoader(agent_name=name, config_dir=resolved_dir)
    resolved = loader.resolve_guidelines(default=DEFAULT_GUIDELINES)
    return resolved.guidelines
