from __future__ import annotations

from pathlib import Path

DEFAULT_AGENT_NAME = "default-mvge"

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

DEFAULT_RUNE_PATHS: list[str] = [
    "~/.agents/.mvgeos/runes",
    "~/.agents/.mvgeos/{agent_name}/runes",
    ".agents/.mvgeos/runes",
]


def resolve_rune_paths(agent_name: str, extension_dir: str | None = None) -> list[Path]:
    """Return expanded rune search paths in precedence order.

    Expands ``{agent_name}`` placeholders and ``~`` home shortcuts.
    An optional ``extension_dir`` is appended last.
    """
    paths = [
        Path(str(p).replace("{agent_name}", agent_name)).expanduser()
        for p in DEFAULT_RUNE_PATHS
    ]
    if extension_dir:
        paths.append(Path(extension_dir).expanduser())
    return paths
