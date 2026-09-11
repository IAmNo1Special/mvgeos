from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mvgeos_runes.types import SkillScope
from typer.testing import CliRunner

from mvgeos_cli.commands import skill as skill_module
from mvgeos_cli.commands.skill import plan_skill_dedupe, skill_app

runner = CliRunner()


@contextmanager
def _isolated_discovery(
    paths: list[tuple[Path, SkillScope]],
) -> Iterator[None]:
    """Point skill discovery at tmp dirs (hermetic, no real home writes)."""
    with (
        patch.object(skill_module, "get_default_skill_paths", return_value=paths),
        patch.object(skill_module, "discover_plugin_skill_paths", return_value=[]),
    ):
        yield


def _write_skill(root: Path, name: str, description: str = "test skill") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nversion: 1.0.0\n---\n",
        encoding="utf-8",
    )
    return skill_dir


def _shadowed_paths(tmp_path: Path) -> list[tuple[Path, SkillScope]]:
    user_skills = tmp_path / "user_skills"
    agent_skills = tmp_path / "agent_skills"
    _write_skill(user_skills, "duplicate-skill", "user scope skill")
    _write_skill(agent_skills, "duplicate-skill", "agent scope skill")
    _write_skill(user_skills, "unique-skill", "only in user scope")
    return [
        (user_skills, SkillScope.USER),
        (agent_skills, SkillScope.AGENT),
    ]


def test_plan_skill_dedupe_finds_shadowed(tmp_path: Path) -> None:
    """Verify the plan flags the agent-scope copy shadowed by user scope."""
    plan = plan_skill_dedupe("tester", skill_paths=_shadowed_paths(tmp_path))

    assert len(plan) == 1
    entry = plan[0]
    assert entry.name == "duplicate-skill"
    assert entry.shadow_scope == SkillScope.AGENT
    assert entry.shadow_dir == tmp_path / "agent_skills" / "duplicate-skill"
    assert entry.winner_scope == SkillScope.USER
    assert entry.winner_dir == tmp_path / "user_skills" / "duplicate-skill"


def test_plan_skill_dedupe_no_shadows(tmp_path: Path) -> None:
    """Verify an empty plan when every skill name is unique."""
    user_skills = tmp_path / "user_skills"
    _write_skill(user_skills, "unique-skill")

    plan = plan_skill_dedupe("tester", skill_paths=[(user_skills, SkillScope.USER)])

    assert plan == []


def test_skill_dedupe_dry_run_lists_without_deleting(tmp_path: Path) -> None:
    """Verify --dry-run reports the shadowed copy and deletes nothing."""
    paths = _shadowed_paths(tmp_path)
    with _isolated_discovery(paths):
        result = runner.invoke(
            skill_app, ["dedupe", "--agent-name", "tester", "--dry-run"]
        )

    assert result.exit_code == 0
    assert "duplicate-skill" in result.output
    assert (tmp_path / "agent_skills" / "duplicate-skill").exists()


def test_skill_dedupe_without_yes_does_not_delete(tmp_path: Path) -> None:
    """Verify the default run is safe and points at --yes."""
    paths = _shadowed_paths(tmp_path)
    with _isolated_discovery(paths):
        result = runner.invoke(skill_app, ["dedupe", "--agent-name", "tester"])

    assert result.exit_code == 0
    assert "--yes" in result.output
    assert (tmp_path / "agent_skills" / "duplicate-skill").exists()


def test_skill_dedupe_yes_removes_only_shadowed(tmp_path: Path) -> None:
    """Verify --yes removes the shadowed copy and keeps the winner."""
    paths = _shadowed_paths(tmp_path)
    with _isolated_discovery(paths):
        result = runner.invoke(skill_app, ["dedupe", "--agent-name", "tester", "--yes"])

    assert result.exit_code == 0
    assert "duplicate-skill" in result.output
    assert not (tmp_path / "agent_skills" / "duplicate-skill").exists()
    assert (tmp_path / "user_skills" / "duplicate-skill").exists()
    assert (tmp_path / "user_skills" / "unique-skill").exists()


def test_skill_dedupe_no_shadows_message(tmp_path: Path) -> None:
    """Verify a friendly message when there is nothing to dedupe."""
    user_skills = tmp_path / "user_skills"
    _write_skill(user_skills, "unique-skill")
    paths = [(user_skills, SkillScope.USER)]
    with _isolated_discovery(paths):
        result = runner.invoke(skill_app, ["dedupe", "--agent-name", "tester"])

    assert result.exit_code == 0
    assert "No shadowed skills" in result.output
