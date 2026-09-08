from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_agent import Mvge
from mvgeos_agent.types import MvgeEventType, SpellStatus
from mvgeos_runes.types import SkillManifest, SkillScope

from coding_mvge.runes.skill_evolution.proposer_mvge import (
    create_proposer_mvge,
    proposer_mvge,
    run_proposer,
    scoped_proposer_context,
)
from coding_mvge.runes.skill_evolution.proposer_mvge.spells.finish import finish
from coding_mvge.runes.skill_evolution.proposer_mvge.spells.read_file import read_file


@pytest.fixture
def tmp_evolution_env(tmp_path: Path):
    edir = tmp_path / "skill_evolution"
    rdir = tmp_path / "raw_experience"
    skills_dir = tmp_path / ".agents" / "skills"
    edir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    with scoped_proposer_context(
        evolution_dir=edir,
        raw_experience_dir=rdir,
        target_skills_dir=skills_dir,
        auto_apply=True,
    ):
        yield tmp_path, edir, rdir, skills_dir


class TestProposerFileBasedConstruction:
    def test_proposer_mvge_is_standalone_mvge_instance(self) -> None:
        assert isinstance(proposer_mvge, Mvge)
        assert proposer_mvge.name == "proposer_mvge"

    def test_proposer_mvge_auto_discovers_spells(self) -> None:
        spell_names = [spell.name for spell in proposer_mvge.spells]
        assert "read_file" in spell_names
        assert "finish" in spell_names

    def test_proposer_mvge_auto_resolves_system_prompt_and_guidelines(self) -> None:
        env = proposer_mvge.environment
        assert "Skill Proposer" in env.resolved_prompt.text
        guidelines_text = "\n".join(env.resolved_guidelines.guidelines)
        assert "Target ONE skill per iteration" in guidelines_text


class TestProposerSpells:
    @pytest.mark.asyncio
    async def test_read_file_within_evolution_and_traces(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, edir, rdir, _ = tmp_evolution_env
        (edir / "index.md").write_text("# Evolution Index\n", encoding="utf-8")
        pat_dir = edir / "patterns"
        pat_dir.mkdir(exist_ok=True)
        (pat_dir / "loop.md").write_text("# Loop Pattern\n", encoding="utf-8")

        traces_dir = rdir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        (traces_dir / "inv_1.json").write_text('{"id": "inv_1"}', encoding="utf-8")

        # Read index
        res1 = await read_file("skill_evolution/index.md")
        assert res1.status == SpellStatus.SUCCESS
        assert "# Evolution Index" in (res1.content or "")

        # Read pattern
        res2 = await read_file("skill_evolution/patterns/loop.md")
        assert res2.status == SpellStatus.SUCCESS
        assert "# Loop Pattern" in (res2.content or "")

        # Read trace via alias traces/<id>
        res3 = await read_file("traces/inv_1.json")
        assert res3.status == SpellStatus.SUCCESS
        assert '{"id": "inv_1"}' in (res3.content or "")

    @pytest.mark.asyncio
    async def test_read_file_raw_experience_candidates(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, _, rdir, _ = tmp_evolution_env
        (rdir / "nested_trace.json").write_text('{"nested": true}', encoding="utf-8")
        sub = rdir / "sub"
        sub.mkdir(exist_ok=True)
        (sub / "trace_glob_find.json").write_text('{"glob": true}', encoding="utf-8")

        # Direct in raw_experience_dir via traces/
        res1 = await read_file("traces/nested_trace.json")
        assert res1.status == SpellStatus.SUCCESS
        assert '{"nested": true}' in (res1.content or "")

        # Via rglob search in raw_experience_dir
        res2 = await read_file("traces/glob_find")
        assert res2.status == SpellStatus.SUCCESS
        assert '{"glob": true}' in (res2.content or "")

    @pytest.mark.asyncio
    async def test_read_file_not_found(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        res = await read_file("skill_evolution/missing.md")
        assert res.status == SpellStatus.ERROR
        assert "not found" in (res.error_message or "").lower()

    @pytest.mark.asyncio
    async def test_read_file_rejects_path_traversal(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        res = await read_file("../../secret.txt")
        assert res.status == SpellStatus.ERROR
        assert (
            "outside allowed scopes" in (res.error_message or "").lower()
            or "not found" in (res.error_message or "").lower()
        )

    @pytest.mark.asyncio
    async def test_finish_no_action_proposal(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, edir, _, _ = tmp_evolution_env
        res = await finish({"action": "no_action"})
        assert res.status == SpellStatus.SUCCESS
        payload = json.loads(res.content or "{}")
        assert payload.get("action") == "no_action"
        assert (edir / "skill-impact.md").exists()

    @pytest.mark.asyncio
    async def test_finish_invalid_json_str(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        res = await finish("not-valid-json{")
        assert res.status == SpellStatus.ERROR
        assert "Invalid JSON" in (res.error_message or "")

    @pytest.mark.asyncio
    async def test_finish_name_validation(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        res1 = await finish({"action": "create", "name": ""})
        assert res1.status == SpellStatus.ERROR
        assert "1-64 characters" in (res1.error_message or "")

        res2 = await finish({"action": "create", "name": "Invalid_Name"})
        assert res2.status == SpellStatus.ERROR
        assert "must match" in (res2.error_message or "")

    @pytest.mark.asyncio
    async def test_finish_create_proposal(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, edir, _, skills_dir = tmp_evolution_env
        proposal = {
            "action": "create",
            "name": "retry-spell",
            "skill_md": "---\nname: retry-spell\ndescription: Retry\n---\n# Retry\n",
            "purpose_md": "# Purpose\nOrigin: retry pattern\n",
        }
        res = await finish(proposal)
        assert res.status == SpellStatus.SUCCESS
        payload = json.loads(res.content or "{}")
        assert payload.get("success") is True
        assert payload.get("name") == "retry-spell"

        # Check files written
        assert (skills_dir / "retry-spell" / "SKILL.md").exists()
        assert (skills_dir / "retry-spell" / "PURPOSE.md").exists()

        # Check impact audit trail
        impact = (edir / "skill-impact.md").read_text(encoding="utf-8")
        assert "retry-spell" in impact
        assert "+++ retry-spell/SKILL.md" in impact

    @pytest.mark.asyncio
    async def test_finish_create_missing_fields(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        res = await finish(
            {"action": "create", "name": "valid-name", "skill_md": "content"}
        )
        assert res.status == SpellStatus.ERROR
        assert "requires both skill_md and purpose_md" in (res.error_message or "")

    @pytest.mark.asyncio
    async def test_finish_patch_proposal_append_and_insert_after(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, edir, _, skills_dir = tmp_evolution_env
        skill_dir = skills_dir / "existing-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        sk_path = skill_dir / "SKILL.md"
        sk_path.write_text(
            "---\nname: existing-skill\n---\n# Section 1\n# Section 3\n",
            encoding="utf-8",
        )

        proposal = {
            "action": "patch",
            "name": "existing-skill",
            "edits": [
                {
                    "op": "insert_after",
                    "target": "# Section 1\n",
                    "content": "# Section 2\n",
                },
                {
                    "op": "append",
                    "content": "# Section 4\n",
                },
            ],
        }
        res = await finish(proposal)
        assert res.status == SpellStatus.SUCCESS
        payload = json.loads(res.content or "{}")
        assert payload.get("success") is True

        content = sk_path.read_text(encoding="utf-8")
        assert "# Section 2" in content
        assert "# Section 4" in content

    @pytest.mark.asyncio
    async def test_finish_patch_validation_and_errors(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, _, _, skills_dir = tmp_evolution_env
        # No edits
        res1 = await finish({"action": "patch", "name": "my-skill", "edits": []})
        assert res1.status == SpellStatus.ERROR

        # Skill not found
        res2 = await finish(
            {
                "action": "patch",
                "name": "non-existent",
                "edits": [{"op": "append", "content": "x"}],
            }
        )
        assert res2.status == SpellStatus.ERROR
        assert "not found for patching" in (res2.error_message or "")

        # Skill exists but replace target not found
        sk = skills_dir / "find-me"
        sk.mkdir(parents=True, exist_ok=True)
        (sk / "SKILL.md").write_text("initial text", encoding="utf-8")

        res3 = await finish(
            {
                "action": "patch",
                "name": "find-me",
                "edits": [
                    {"op": "replace", "target": "missing target", "content": "new"}
                ],
            }
        )
        assert res3.status == SpellStatus.ERROR
        assert "replace target not found" in (res3.error_message or "")

        # insert_after target not found
        res4 = await finish(
            {
                "action": "patch",
                "name": "find-me",
                "edits": [
                    {"op": "insert_after", "target": "missing target", "content": "new"}
                ],
            }
        )
        assert res4.status == SpellStatus.ERROR
        assert "insert_after target not found" in (res4.error_message or "")

        # Unknown op
        res5 = await finish(
            {
                "action": "patch",
                "name": "find-me",
                "edits": [{"op": "unsupported", "content": "new"}],
            }
        )
        assert res5.status == SpellStatus.ERROR
        assert "Unknown patch op" in (res5.error_message or "")

    @pytest.mark.asyncio
    async def test_finish_unknown_action(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        res = await finish({"action": "explode", "name": "test-name"})
        assert res.status == SpellStatus.ERROR
        assert "Unknown proposal action" in (res.error_message or "")


class TestProposerAutonomousLifecycle:
    @pytest.mark.asyncio
    async def test_run_proposer_emits_authentic_lifecycle_events(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        _, edir, rdir, skills_dir = tmp_evolution_env
        (edir / "index.md").write_text("# Evolution Index\n", encoding="utf-8")
        (edir / "skill-impact.md").write_text("# Past Proposals\n", encoding="utf-8")
        (edir / "logs.md").write_text("Turn logs...", encoding="utf-8")

        events_received = []

        agent = create_proposer_mvge(api_key="test-key")
        agent.event_bus.subscribe(lambda ev: events_received.append(ev))

        proposal_dict = {
            "action": "create",
            "name": "lifecycle-skill",
            "skill_md": "---\nname: lifecycle-skill\n---\n# Content\n",
            "purpose_md": "# Purpose\n",
        }

        mock_response = (
            f"I have reviewed the evolution index.\n"
            f"```json\n{json.dumps(proposal_dict)}\n```"
        )

        async def fake_run(prompt: str):
            agent.event_bus.emit(MvgeEventType.AGENT_START, {"name": "proposer_mvge"})
            agent.event_bus.emit(MvgeEventType.TURN_START, {"turn": 1})
            agent.event_bus.emit(MvgeEventType.AGENT_END, {"success": True})
            return MagicMock(content=[{"type": "text", "text": mock_response}])

        agent.run = AsyncMock(side_effect=fake_run)

        result = await run_proposer(
            mvge=agent,
            evolution_dir=edir,
            raw_experience_dir=rdir,
            target_skills_dir=skills_dir,
            auto_apply=True,
            user_prompt=None,
        )
        assert result.get("success") is True
        assert result.get("name") == "lifecycle-skill"

        event_types = [e.type for e in events_received]
        assert MvgeEventType.AGENT_START in event_types
        assert MvgeEventType.AGENT_END in event_types

    @pytest.mark.asyncio
    async def test_run_proposer_plain_text_fallback(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        agent = create_proposer_mvge(api_key="test-key")
        inv = MagicMock(spec=[])
        inv.text = "Just normal conversational text."
        agent.run = AsyncMock(return_value=inv)

        result = await run_proposer(
            mvge=agent,
            user_prompt="Custom prompt",
        )
        assert result.get("success") is True
        assert result.get("action") == "no_action"
        assert result.get("content") == "Just normal conversational text."

    @pytest.mark.asyncio
    async def test_run_proposer_malformed_json_fallback(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        agent = create_proposer_mvge(api_key="test-key")
        inv = MagicMock(content="```json\n{not-valid-json\n```")
        agent.run = AsyncMock(return_value=inv)

        result = await run_proposer(
            mvge=agent,
            user_prompt="Custom prompt",
        )
        assert result.get("success") is True
        assert result.get("action") == "no_action"

    @pytest.mark.asyncio
    async def test_read_file_raw_dir_direct_and_read_error(
        self, tmp_evolution_env: tuple[Path, Path, Path, Path]
    ) -> None:
        from unittest.mock import patch

        _, _, rdir, _ = tmp_evolution_env
        direct_file = rdir / "direct.txt"
        direct_file.write_text("direct content", encoding="utf-8")

        res = await read_file("direct.txt")
        assert res.status == SpellStatus.SUCCESS
        assert "direct content" in (res.content or "")

        with patch.object(Path, "read_text", side_effect=OSError("Disk failure")):
            res_err = await read_file("direct.txt")
            assert res_err.status == SpellStatus.ERROR
            assert "Disk failure" in (res_err.error_message or "")


class TestProposerMultiScopeResolution:
    @pytest.mark.asyncio
    async def test_patch_project_scope_in_place(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "project" / ".agents" / "skills" / "proj-skill"
        proj_dir.mkdir(parents=True)
        sk_file = proj_dir / "SKILL.md"
        sk_file.write_text("# Project Skill Original\n", encoding="utf-8")

        manifest = SkillManifest(
            name="proj-skill",
            description="project skill",
            scope=SkillScope.PROJECT,
            path=str(proj_dir),
        )

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=tmp_path / "agent_skills",
            project_skills_dir=proj_dir.parent,
            available_skills=[manifest],
            auto_apply=True,
        ):
            res = await finish(
                {
                    "action": "patch",
                    "name": "proj-skill",
                    "edits": [{"op": "append", "content": "# Added in project\n"}],
                }
            )
            assert res.status == SpellStatus.SUCCESS
            payload = json.loads(res.content or "{}")
            assert payload.get("scope") == "project"
            assert "# Added in project" in sk_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_patch_agent_scope_in_place(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent" / "skills" / "agent-skill"
        agent_dir.mkdir(parents=True)
        sk_file = agent_dir / "SKILL.md"
        sk_file.write_text("# Agent Skill Original\n", encoding="utf-8")

        manifest = SkillManifest(
            name="agent-skill",
            description="agent skill",
            scope=SkillScope.AGENT,
            path=str(agent_dir),
        )

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=agent_dir.parent,
            available_skills=[manifest],
            auto_apply=True,
        ):
            res = await finish(
                {
                    "action": "patch",
                    "name": "agent-skill",
                    "edits": [{"op": "append", "content": "# Added in agent\n"}],
                }
            )
            assert res.status == SpellStatus.SUCCESS
            payload = json.loads(res.content or "{}")
            assert payload.get("scope") == "agent"
            assert "# Added in agent" in sk_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_patch_user_scope_in_place(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user" / "skills" / "user-skill"
        user_dir.mkdir(parents=True)
        sk_file = user_dir / "SKILL.md"
        sk_file.write_text("# User Skill Original\n", encoding="utf-8")

        manifest = SkillManifest(
            name="user-skill",
            description="user skill",
            scope=SkillScope.USER,
            path=str(user_dir),
        )

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=tmp_path / "agent_skills",
            project_skills_dir=tmp_path / "proj_skills",
            available_skills=[manifest],
            auto_apply=True,
        ):
            # Without fork_to_project: patch in-place in user scope
            res = await finish(
                {
                    "action": "patch",
                    "name": "user-skill",
                    "edits": [{"op": "append", "content": "# Universal patch\n"}],
                }
            )
            assert res.status == SpellStatus.SUCCESS
            payload = json.loads(res.content or "{}")
            assert payload.get("scope") == "user"
            assert "# Universal patch" in sk_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_fork_user_scope_to_project(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user" / "skills" / "forkable-skill"
        user_dir.mkdir(parents=True)
        (user_dir / "SKILL.md").write_text("# Original User Skill\n", encoding="utf-8")
        (user_dir / "helper.sh").write_text("echo hello\n", encoding="utf-8")

        proj_skills_dir = tmp_path / "project" / ".agents" / "skills"
        proj_skills_dir.mkdir(parents=True)

        manifest = SkillManifest(
            name="forkable-skill",
            description="forkable skill",
            scope=SkillScope.USER,
            path=str(user_dir),
        )

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=tmp_path / "agent_skills",
            project_skills_dir=proj_skills_dir,
            available_skills=[manifest],
            auto_apply=True,
        ):
            res = await finish(
                {
                    "action": "patch",
                    "name": "forkable-skill",
                    "fork_to_project": True,
                    "edits": [{"op": "append", "content": "# Repo-specific rule\n"}],
                }
            )
            assert res.status == SpellStatus.SUCCESS
            payload = json.loads(res.content or "{}")
            assert payload.get("scope") == "project"

            # User file was NOT mutated
            assert "# Repo-specific rule" not in (user_dir / "SKILL.md").read_text(
                encoding="utf-8"
            )

            # Project copy was created and patched
            project_copy = proj_skills_dir / "forkable-skill" / "SKILL.md"
            assert project_copy.exists()
            assert "# Repo-specific rule" in project_copy.read_text(encoding="utf-8")
            assert (proj_skills_dir / "forkable-skill" / "helper.sh").exists()

    @pytest.mark.asyncio
    async def test_create_project_vs_agent_scope(self, tmp_path: Path) -> None:
        proj_skills_dir = tmp_path / "project" / ".agents" / "skills"
        agent_skills_dir = tmp_path / "agent" / "skills"
        proj_skills_dir.mkdir(parents=True)
        agent_skills_dir.mkdir(parents=True)

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=agent_skills_dir,
            project_skills_dir=proj_skills_dir,
            auto_apply=True,
        ):
            # Create with scope: project
            res1 = await finish(
                {
                    "action": "create",
                    "name": "new-proj-skill",
                    "scope": "project",
                    "skill_md": "# Proj Skill\n",
                    "purpose_md": "# Purpose\n",
                }
            )
            assert res1.status == SpellStatus.SUCCESS
            assert (proj_skills_dir / "new-proj-skill" / "SKILL.md").exists()

            # Create with scope: agent
            res2 = await finish(
                {
                    "action": "create",
                    "name": "new-agent-skill",
                    "scope": "agent",
                    "skill_md": "# Agent Skill\n",
                    "purpose_md": "# Purpose\n",
                }
            )
            assert res2.status == SpellStatus.SUCCESS
            assert (agent_skills_dir / "new-agent-skill" / "SKILL.md").exists()

    @pytest.mark.asyncio
    async def test_read_file_from_skills(self, tmp_path: Path) -> None:
        proj_skills_dir = tmp_path / "project" / ".agents" / "skills"
        sk_dir = proj_skills_dir / "readable-skill"
        sk_dir.mkdir(parents=True)
        (sk_dir / "SKILL.md").write_text("# Readable Skill Content\n", encoding="utf-8")

        manifest = SkillManifest(
            name="readable-skill",
            description="readable",
            scope=SkillScope.PROJECT,
            path=str(sk_dir),
        )

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=tmp_path / "agent_skills",
            project_skills_dir=proj_skills_dir,
            available_skills=[manifest],
            auto_apply=True,
        ):
            res = await read_file("skills/readable-skill/SKILL.md")
            assert res.status == SpellStatus.SUCCESS
            assert "# Readable Skill Content" in (res.content or "")

    @pytest.mark.asyncio
    async def test_run_proposer_includes_skills_in_prompt(self, tmp_path: Path) -> None:
        edir = tmp_path / "skill_evolution"
        edir.mkdir()
        (edir / "index.md").write_text("# Index\n", encoding="utf-8")
        agent = create_proposer_mvge(api_key="test-key")

        captured_prompt = []

        async def fake_run(prompt: str):
            captured_prompt.append(prompt)
            return MagicMock(
                content=[
                    {"type": "text", "text": '```json\n{"action": "no_action"}\n```'}
                ]
            )

        agent.run = AsyncMock(side_effect=fake_run)

        manifest = SkillManifest(
            name="demo-skill",
            description="demo description",
            scope=SkillScope.PROJECT,
            path=str(tmp_path),
        )

        res = await run_proposer(
            mvge=agent,
            evolution_dir=edir,
            available_skills=[manifest],
            user_prompt=None,
        )
        assert res.get("success") is True
        assert len(captured_prompt) == 1
        assert "demo-skill [project]: demo description" in captured_prompt[0]

    @pytest.mark.asyncio
    async def test_finish_fallback_patch_targets(self, tmp_path: Path) -> None:
        proj_skills_dir = tmp_path / "project" / ".agents" / "skills"
        p_sk = proj_skills_dir / "p-fallback"
        p_sk.mkdir(parents=True)
        (p_sk / "SKILL.md").write_text("# P Fallback Original\n", encoding="utf-8")

        agent_skills_dir = tmp_path / "agent" / "skills"
        a_sk = agent_skills_dir / "a-fallback"
        a_sk.mkdir(parents=True)
        (a_sk / "SKILL.md").write_text("# A Fallback Original\n", encoding="utf-8")

        with scoped_proposer_context(
            evolution_dir=tmp_path / "skill_evolution",
            raw_experience_dir=tmp_path / "raw_experience",
            target_skills_dir=agent_skills_dir,
            project_skills_dir=proj_skills_dir,
            available_skills={},
            auto_apply=True,
        ):
            # Patch project fallback
            res1 = await finish(
                {
                    "action": "patch",
                    "name": "p-fallback",
                    "edits": [{"op": "append", "content": "# P Edited\n"}],
                }
            )
            assert res1.status == SpellStatus.SUCCESS
            assert "# P Edited" in (p_sk / "SKILL.md").read_text(encoding="utf-8")

            # Patch agent fallback
            res2 = await finish(
                {
                    "action": "patch",
                    "name": "a-fallback",
                    "edits": [{"op": "append", "content": "# A Edited\n"}],
                }
            )
            assert res2.status == SpellStatus.SUCCESS
            assert "# A Edited" in (a_sk / "SKILL.md").read_text(encoding="utf-8")
