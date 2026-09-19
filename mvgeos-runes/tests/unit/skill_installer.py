"""Unit tests for the skill installer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mvgeos_runes.skill_installer import install_skill


def _create_mock_skill_dir(path: Path, name: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"# {name}\n\nTest skill.\n", encoding="utf-8")
    return path


def test_install_skill_from_local_path(tmp_path: Path) -> None:
    source = _create_mock_skill_dir(tmp_path / "my-skill", "my-skill")
    target = tmp_path / "skills"

    dest = install_skill(str(source), target_dir=target)

    assert dest == target / "my-skill"
    assert (dest / "SKILL.md").is_file()


def test_install_skill_from_local_path_with_name(tmp_path: Path) -> None:
    source = _create_mock_skill_dir(tmp_path / "src-skill", "my-skill")
    target = tmp_path / "skills"

    dest = install_skill(str(source), name="renamed-skill", target_dir=target)

    assert dest == target / "renamed-skill"
    assert (dest / "SKILL.md").is_file()


def test_install_skill_rejects_missing_skill_md(tmp_path: Path) -> None:
    source = tmp_path / "not-a-skill"
    source.mkdir()
    target = tmp_path / "skills"

    with pytest.raises(ValueError, match="SKILL.md"):
        install_skill(str(source), target_dir=target)


def test_install_skill_rejects_nonexistent_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        install_skill(str(tmp_path / "nope"), target_dir=tmp_path / "skills")


def test_install_skill_from_git_url(tmp_path: Path) -> None:
    target = tmp_path / "skills"

    def fake_clone(url: str, dest: Path) -> None:
        _create_mock_skill_dir(dest, "cloned-skill")

    with patch(
        "mvgeos_runes.skill_installer._clone_git_repo", side_effect=fake_clone
    ):
        dest = install_skill(
            "https://github.com/example/skill-repo.git", target_dir=target
        )

    assert dest == target / "skill-repo"
    assert (dest / "SKILL.md").is_file()


def test_install_skill_refuses_overwrite(tmp_path: Path) -> None:
    source = _create_mock_skill_dir(tmp_path / "my-skill", "my-skill")
    target = tmp_path / "skills"
    install_skill(str(source), target_dir=target)

    with pytest.raises(ValueError, match="already installed"):
        install_skill(str(source), target_dir=target)
