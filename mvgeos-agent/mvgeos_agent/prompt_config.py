from __future__ import annotations

from pathlib import Path

_SYSTEM_PROMPT_BODY = (
    "You are Mvge, a concise AI coding agent. "
    "You have access to spells (tools) to read files, write code, "
    "edit files, run shell commands, search code, and navigate the filesystem."
)

DEFAULT_SYSTEM_PROMPT = (
    _SYSTEM_PROMPT_BODY + "\n\n"
    "Guidelines:\n"
    "- Be concise. Give short answers unless asked for detail.\n"
    "- Do not speculate or predict the future. "
    "If you don't know something or lack a capability, say so in one "
    "sentence and suggest how you could be equipped to help "
    "(e.g. a web search tool, a new spell, a skill, etc.).\n"
    "- Do not add fluff, filler, or cheerful commentary.\n"
    "- Show file paths when working with files.\n"
    "- When executing shell commands, explain what they do briefly.\n"
    "- Use spells when you need filesystem or command access.\n"
    "- If the user asks a coding question, write working code.\n"
    "- If the user asks a non-coding question, answer briefly or suggest "
    "how you could be equipped to help."
)

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


def build_system_prompt(
    spells: list[str],
    config_dir: Path | None = None,
    cwd: str = "",
    custom_prompt: str = "",
    custom: str = "",
    append_text: str = "",
    context_files: list[dict[str, str]] | None = None,
    name: str = "coding-agent",
) -> str:
    """Build a system prompt with spells, guidelines, and optional context files."""
    if config_dir is not None and config_dir.exists():
        system_md = config_dir / "SYSTEM.md"
        if system_md.exists():
            custom_prompt = system_md.read_text(encoding="utf-8").strip()
        _ = config_dir / "GUIDELINES.md"
        if Path("GUIDELINES.md").exists():
            lines = (
                config_dir.joinpath("GUIDELINES.md")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()
            )
            _ = [line.lstrip("- ").strip() for line in lines if line.strip()]

    parts = [custom_prompt or DEFAULT_SYSTEM_PROMPT]

    spell_list = "\n".join(f"  - {s}" for s in spells) if spells else "  (none)"
    parts.append(f"\nActive spells:\n{spell_list}")

    parts.append("\nGuidelines:")
    for g in DEFAULT_GUIDELINES:
        parts.append(f"- {g}")

    if cwd:
        parts.append(f"\nCurrent working directory: {cwd}")

    return "\n".join(parts)


def _default_config_dir(name: str) -> Path:
    return Path(f"~/.agents/.mvgeos/{name}").expanduser()


def ensure_config_files(name: str) -> Path:
    """Ensure SYSTEM.md and GUIDELINES.md exist for the given agent name."""
    config_dir = _default_config_dir(name)
    config_dir.mkdir(parents=True, exist_ok=True)

    system_path = config_dir / "SYSTEM.md"

    if not system_path.exists():
        system_path.write_text(
            "You are Mvge, a concise AI coding agent. "
            "You have access to spells (tools) to read files, write code, "
            "edit files, run shell commands, search code, and navigate the "
            "filesystem.\n\n"
            "Guidelines:\n"
            "- Be concise. Give short answers unless asked for detail.\n"
            "- Do not speculate or predict the future. "
            "If you don't know something or lack a capability, say so in one "
            "sentence and suggest how you could be equipped to help "
            "(e.g. a web search tool, a new spell, a skill, etc.).\n"
            "- Do not add fluff, filler, or cheerful commentary.\n"
            "- Show file paths when working with files.\n"
            "- When executing shell commands, explain what they do briefly.\n"
            "- Use spells when you need filesystem or command access.\n"
            "- If the user asks a coding question, write working code.\n"
            "- If the user asks a non-coding question, answer briefly or suggest "
            "how you could be equipped to help.",
            encoding="utf-8",
        )

    config_dir.joinpath("GUIDELINES.md").touch(exist_ok=True)

    return config_dir


def load_system_prompt(
    name: str,
    custom: str = "",
    config_dir: Path | None = None,
    spells: list[str] | None = None,
) -> str:
    """Load the system prompt from config directory, falling back to default."""
    prompt: str | None = None

    if config_dir is not None and config_dir.exists():
        try:
            system_md = config_dir / "SYSTEM.md"
            if system_md.exists():
                prompt = system_md.read_text(encoding="utf-8").strip()
            guidelines_md = config_dir / "GUIDELINES.md"
            if guidelines_md.exists():
                guidelines_text = guidelines_md.read_text(encoding="utf-8").strip()
                if guidelines_text:
                    return (
                        (prompt or _SYSTEM_PROMPT_BODY)
                        + "\n\nGuidelines:\n"
                        + guidelines_text
                    )
            if prompt is not None:
                return prompt
        except OSError:
            prompt = None

    if custom:
        return custom

    config_path = Path(f"~/.agents/.mvgeos/{name}/SYSTEM.md").expanduser()

    if not config_path.exists():
        prompt = DEFAULT_SYSTEM_PROMPT
    else:
        try:
            prompt = config_path.read_text(encoding="utf-8").strip()
        except OSError:
            prompt = DEFAULT_SYSTEM_PROMPT

    if spells:
        spell_list = "\n".join(f"  - {s}" for s in spells)
        prompt += f"\n\nActive spells:\n{spell_list}"

    return prompt


def load_guidelines(name: str) -> list[str]:
    """Load guidelines from config directory, falling back to defaults."""
    if not Path(f"~/.agents/.mvgeos/{name}/GUIDELINES.md").expanduser().exists():
        return list(DEFAULT_GUIDELINES)

    try:
        content = (
            Path(f"~/.agents/.mvgeos/{name}/GUIDELINES.md")
            .expanduser()
            .read_text(encoding="utf-8")
            .strip()
        )
        if not content:
            return list(DEFAULT_GUIDELINES)
        lines = [
            line.lstrip("- ").strip() for line in content.splitlines() if line.strip()
        ]
        return [line for line in lines if line]
    except OSError:
        return list(DEFAULT_GUIDELINES)
