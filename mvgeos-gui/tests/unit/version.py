"""Unit tests for the mvgeos-gui package version."""

from __future__ import annotations

import importlib.metadata

import pytest

import mvgeos_gui


def test_version_matches_installed_distribution() -> None:
    """The GUI must report its installed version, never a hardcoded one."""
    installed = importlib.metadata.version("mvgeos-gui")
    assert mvgeos_gui.__version__ == installed
    assert mvgeos_gui.__version__ != "1.1.0"


def test_version_falls_back_to_unknown_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without installed distribution metadata the version is "unknown".

    The helper is called directly (no importlib.reload): NiceGUI's test
    plugin pops page-route modules such as mvgeos_gui from sys.modules
    after each User test, so reloading the package is not reliable in
    the full suite.
    """

    def _missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", _missing)
    assert mvgeos_gui._installed_version() == "unknown"
