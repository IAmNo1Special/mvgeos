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
    with patch.object(
        skill_module, "get_prioritized_skill_search_paths", return_value=paths
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


def test_skill_list_empty(tmp_path: Path) -> None:
    with _isolated_discovery([]):
        result = runner.invoke(skill_app, ["list"])
    assert result.exit_code == 0
    assert "No skills found" in result.output


def test_skill_list_with_skills(tmp_path: Path) -> None:
    user_skills = tmp_path / "user_skills"
    _write_skill(user_skills, "my-tool", "Does useful things")
    paths = [(user_skills, SkillScope.USER)]
    with _isolated_discovery(paths):
        result = runner.invoke(skill_app, ["list"])
    assert result.exit_code == 0
    assert "my-tool" in result.output
    assert "Does useful things" in result.output


def test_skill_validate_success(tmp_path: Path) -> None:
    skill_dir = tmp_path / "calc-tool"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: calc-tool\ndescription: A calculation tool\n---\n"
        "# Calc\nUse calculator.",
        encoding="utf-8",
    )
    result = runner.invoke(skill_app, ["validate", str(skill_dir)])
    assert result.exit_code == 0
    assert "OK:" in result.output
    assert "calc-tool" in result.output


def test_skill_validate_missing_skill_md(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty-tool"
    empty_dir.mkdir()
    result = runner.invoke(skill_app, ["validate", str(empty_dir)])
    assert result.exit_code == 1
    assert "FAIL:" in result.output
    assert "Missing SKILL.md" in result.output


def test_skill_validate_invalid_name(tmp_path: Path) -> None:
    bad_dir = tmp_path / "Bad_Name"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text(
        "---\nname: Bad_Name\ndescription: Invalid uppercase name\n---\nBody",
        encoding="utf-8",
    )
    result = runner.invoke(skill_app, ["validate", str(bad_dir)])
    assert result.exit_code == 1
    assert "FAIL:" in result.output


def test_skill_validate_path_escape(tmp_path: Path) -> None:
    escape_dir = tmp_path / "escape-tool"
    escape_dir.mkdir()
    (escape_dir / "SKILL.md").write_text(
        "---\nname: escape-tool\ndescription: Escapes root\n---\nRead ../secret.txt",
        encoding="utf-8",
    )
    result = runner.invoke(skill_app, ["validate", str(escape_dir)])
    assert result.exit_code == 1
    assert "FAIL:" in result.output
    assert "path_escape" in result.output
