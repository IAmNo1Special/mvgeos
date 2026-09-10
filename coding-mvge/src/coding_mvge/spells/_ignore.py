from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
        "dist",
        "build",
        ".coverage",
    }
)


def is_ignored_dir_name(name: str) -> bool:
    """Whether a single directory name is ignored by default."""
    return name in DEFAULT_IGNORED_DIRS


def is_ignored_path(path: Path) -> bool:
    """Whether any part of a path crosses a default-ignored directory."""
    return any(part in DEFAULT_IGNORED_DIRS for part in path.parts)


def default_is_excluded(path: Path, is_dir: bool) -> bool:
    """Default walker predicate: prune default-ignored directories.

    Explicit paths are always honored by callers; this predicate only
    prunes descent *below* the given search root. File-level filtering
    is reserved for a future ignore-file-backed predicate.
    """
    return is_dir and is_ignored_dir_name(path.name)


IsExcluded = Callable[[Path, bool], bool]

__all__ = [
    "DEFAULT_IGNORED_DIRS",
    "IsExcluded",
    "default_is_excluded",
    "is_ignored_dir_name",
    "is_ignored_path",
]
