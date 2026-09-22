"""MvgeOS Desktop GUI package powered by NiceGUI."""

from __future__ import annotations

import importlib.metadata


def _installed_version() -> str:
    """Return the installed distribution version ("unknown" if absent)."""
    try:
        return importlib.metadata.version("mvgeos-gui")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


__version__ = _installed_version()
