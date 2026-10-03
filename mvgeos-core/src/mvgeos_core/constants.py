from __future__ import annotations

import os
from pathlib import Path

DEFAULT_AGENT_NAME = "default-mvge"

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

#: Environment variable that relocates the global ``.agents`` layer. The
#: default is ``~/.agents``; setting this moves every global-layer read and
#: write, which is what makes isolated runs possible.
GLOBAL_DIR_ENV = "MVGEOS_GLOBAL_DIR"


def sessions_dir() -> Path:
    """Tome storage: ``<global>/sessions``.

    A function rather than a module constant so the override is read when
    it is needed, not frozen at import. The previous
    ``DEFAULT_SESSION_DIR`` was resolved once during import and could not
    be redirected afterwards.
    """
    return global_agents_dir() / "sessions"


def agents_dir() -> Path:
    """Installed agent packages: ``<global>/agents``."""
    return global_agents_dir() / "agents"


def agent_dir(name: str) -> Path:
    """One agent's directory: ``<global>/agents/<name>``."""
    return agents_dir() / name


def agent_extensions_dir(name: str) -> Path:
    """Agent-scope rune directory: ``<global>/agents/<name>/extensions``."""
    return agent_dir(name) / "extensions"


def agent_skills_dir(name: str) -> Path:
    """Agent-scope skills directory: ``<global>/agents/<name>/skills``."""
    return agent_dir(name) / "skills"


def skills_dir() -> Path:
    """User-scope skills: ``<global>/skills``."""
    return global_agents_dir() / "skills"


def auth_dir() -> Path:
    """Credential store: ``<global>/auth``."""
    return global_agents_dir() / "auth"


def auth_file(provider: str) -> Path:
    """One provider's credential file: ``<global>/auth/<provider>.json``."""
    return auth_dir() / f"{provider}.json"


def approval_dir() -> Path:
    """Approval policy and grants: ``<global>/approval``."""
    return global_agents_dir() / "approval"


def models_file() -> Path:
    """Model cache: ``<global>/models.json``."""
    return global_agents_dir() / "models.json"


def history_file() -> Path:
    """REPL history: ``<global>/history``."""
    return global_agents_dir() / "history"


def global_file(name: str) -> Path:
    """A file directly in the global layer: ``<global>/<name>``."""
    return global_agents_dir() / name


#: Project-layer rune directory, anchored to an explicit project directory
#: at resolve time. Never resolved against the ambient working directory.
PROJECT_RUNE_PATH = ".agents/extensions"


def global_agents_dir() -> Path:
    """The global ``.agents`` directory: ``$MVGEOS_GLOBAL_DIR`` or ``~/.agents``.

    The single resolver for the global layer. Every global-layer path is
    derived here rather than spelled out, because the install path and the
    discovery path resolving differently is what allows a rune to install
    successfully and then load nowhere.
    """
    override = os.environ.get(GLOBAL_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path("~/.agents").expanduser()


def extensions_dir() -> Path:
    """The user-scope rune directory: ``<global>/extensions``."""
    return global_agents_dir() / "extensions"


def default_rune_paths(
    agent_name: str, global_dir: str | Path | None = None
) -> list[Path]:
    """The user and agent rune layers, in precedence order.

    ``global_dir`` overrides the global layer when given, else
    ``$MVGEOS_GLOBAL_DIR``, else ``~/.agents``.
    """
    global_root = (
        Path(global_dir).expanduser() if global_dir is not None else global_agents_dir()
    )
    return [
        global_root / "extensions",
        global_root / "agents" / agent_name / "extensions",
    ]


def resolve_rune_paths(
    agent_name: str,
    extension_dir: str | None = None,
    project_dir: str | Path | None = None,
    global_dir: str | Path | None = None,
) -> list[Path]:
    """Return expanded rune search paths in precedence order.

    Expands ``{agent_name}`` placeholders and ``~`` home shortcuts. The
    global layer comes from ``global_dir`` when given, else
    ``$MVGEOS_GLOBAL_DIR``, else ``~/.agents``. The project layer
    (``.agents/extensions``) is anchored to the given ``project_dir`` and
    omitted entirely when no project directory is given, so the ambient
    working directory can never leak into the search paths. An optional
    ``extension_dir`` is appended last.
    """
    paths = default_rune_paths(agent_name, global_dir)
    if project_dir is not None:
        anchor = Path(project_dir).expanduser()
        if not anchor.is_absolute():
            anchor = Path.cwd() / anchor
        paths.append(anchor / PROJECT_RUNE_PATH)
    if extension_dir:
        paths.append(Path(extension_dir).expanduser())
    return paths


resolve_extension_paths = resolve_rune_paths
