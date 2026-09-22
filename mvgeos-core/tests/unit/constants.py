"""Unit tests for mvgeos_core.constants rune path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mvgeos_core.constants import resolve_rune_paths


def test_project_layer_omitted_without_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No project_dir means no project layer — never ambient CWD.

    Regression: the project entry used to be the CWD-relative
    ``.agents/extensions``, so a process launched with its working
    directory at the real home silently loaded the real home's runes
    even with HOME isolated elsewhere.
    """
    (tmp_path / ".agents" / "extensions").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    paths = resolve_rune_paths("test-agent")

    assert all(p.is_absolute() for p in paths)
    assert Path(".agents/extensions") not in paths


def test_project_layer_anchored_to_project_dir(tmp_path) -> None:
    """An explicit project_dir anchors the project layer beneath it."""
    project = tmp_path / "project"
    (project / ".agents" / "extensions").mkdir(parents=True)

    paths = resolve_rune_paths("test-agent", project_dir=project)

    assert paths[2] == project / ".agents" / "extensions"
    assert paths[2].is_absolute()


def test_project_layer_accepts_str_project_dir(tmp_path) -> None:
    """String project dirs anchor the same as Path ones."""
    project = tmp_path / "project"
    project.mkdir()

    paths = resolve_rune_paths("test-agent", project_dir=str(project))

    assert paths[2] == project / ".agents" / "extensions"


def test_project_layer_keeps_position_before_extension_dir(tmp_path) -> None:
    """Precedence order is unchanged: home, agent, project, extension_dir."""
    project = tmp_path / "project"
    project.mkdir()

    paths = resolve_rune_paths("test-agent", "/ext", project_dir=project)

    assert paths[2] == project / ".agents" / "extensions"
    assert paths[3] == Path("/ext")
