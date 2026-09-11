from __future__ import annotations

from pathlib import Path

import pytest
from mvgeos_core.sandbox import MvgeSandbox
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext


@pytest.fixture
def runner():
    r = RuneRunner(sandbox_factory=MvgeSandbox)
    r.bind_context(
        RuneContext(
            cwd=str(Path.cwd()), mode="test", agent_name="coding_mvge", api_key="test"
        )
    )
    return r


@pytest.fixture
def skill_evolution_rune_loaded(runner):
    from coding_mvge.runes.skill_evolution import rune_factory

    api = runner.create_api("skill_evolution")
    rune_factory(api)
    return runner


class TestSkillEvolutionRuneIntegration:
    def test_rune_loads_spells(self, skill_evolution_rune_loaded):
        spells = {
            s.name for s in skill_evolution_rune_loaded.get_all_registered_spells()
        }
        # Only admin/export spells are registered as spells; evolution store is not an
        # inference tool
        assert "skill_evolution_consolidate" in spells
        assert "skill_evolution_export" in spells
        # Crucial WikiSkill invariant: no query/list/propose spells pollute the
        # inference agent
        assert {
            "query_evolution",
            "propose_skill_update",
            "list_evolution",
        }.isdisjoint(spells)

    def test_rune_loads_commands(self, skill_evolution_rune_loaded):
        cmds = {c.name for c in skill_evolution_rune_loaded.get_commands()}
        assert {
            "skill-evolution-consolidate",
            "skill-evolution-export",
            "skill-evolution-stats",
            "skill-evolution-propose",
        }.issubset(cmds)

    def test_rune_hooks_registered(self, skill_evolution_rune_loaded):
        from mvgeos_runes.types import SigilHook

        for hook in [
            SigilHook.AFTER_INVOCATION,
            SigilHook.TURN_END,
            SigilHook.SESSION_SHUTDOWN,
            SigilHook.SESSION_START,
        ]:
            assert len(skill_evolution_rune_loaded.get_sigil_handlers(hook)) > 0

        # BEFORE_MVGE_START is stripped to preserve pure skill-based inference
        assert (
            len(
                skill_evolution_rune_loaded.get_sigil_handlers(
                    SigilHook.BEFORE_MVGE_START
                )
            )
            == 0
        )

    @pytest.mark.asyncio
    async def test_system_prompt_not_polluted(self, skill_evolution_rune_loaded):
        from mvgeos_runes.types import (
            BeforeMvgeStartData,
            SigilHook,
        )

        data = BeforeMvgeStartData(
            base_prompt="Base system prompt.",
            spell_names=[],
            config_dir="",
            custom_prompt="",
            agent_name="coding_mvge",
            cwd="",
        )
        result = await skill_evolution_rune_loaded.emit_chain(
            SigilHook.BEFORE_MVGE_START, data
        )
        assert result.base_prompt == "Base system prompt."
        assert "Skill Evolution" not in result.base_prompt

    @pytest.mark.asyncio
    async def test_consolidate_spell_no_llm(self, skill_evolution_rune_loaded):
        spells = {
            s.name: s for s in skill_evolution_rune_loaded.get_all_registered_spells()
        }
        spell = spells["skill_evolution_consolidate"]
        with pytest.raises(RuntimeError, match="No LLM completion function"):
            await spell.execute(
                spell_cast_id="t1",
                params={"force": True, "current_turn": 1},
                signal=None,
                on_update=None,
            )

    @pytest.mark.asyncio
    async def test_store_queries_and_listing(self, skill_evolution_rune_loaded):
        store = getattr(skill_evolution_rune_loaded, "_skill_evolution_store", None)
        assert store is not None
        index = await store.read_index()
        assert isinstance(index, str)

    @pytest.mark.asyncio
    async def test_propose_skill_via_subagent(
        self, skill_evolution_rune_loaded, tmp_path
    ):
        import json
        import shutil
        from pathlib import Path

        from mvgeos_core.spells import SpellStatus

        from coding_mvge.runes.skill_evolution.proposer_mvge.mvge import (
            scoped_proposer_context,
        )
        from coding_mvge.runes.skill_evolution.proposer_mvge.spells.finish import finish

        agent_skills = (
            Path.home()
            / ".agents"
            / ".mvgeos"
            / "coding_mvge"
            / "skills"
            / "demo-skill"
        )
        agent_skills.mkdir(parents=True, exist_ok=True)
        (agent_skills / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: demo skill\n---\n\n# Demo\n",
            encoding="utf-8",
        )
        (agent_skills / "PURPOSE.md").write_text("# Purpose\n", encoding="utf-8")

        with scoped_proposer_context(
            target_skills_dir=agent_skills.parent, auto_apply=True
        ):
            try:
                res = await finish(
                    {
                        "name": "demo-skill",
                        "action": "patch",
                        "edits": [{"op": "append", "content": "\npatched"}],
                    }
                )
                assert res.status == SpellStatus.SUCCESS
                payload = json.loads(res.content or "{}")
                assert payload.get("success") is True
                assert payload.get("action") == "patch"
                assert "patched" in (agent_skills / "SKILL.md").read_text(
                    encoding="utf-8"
                )

                bad = await finish(
                    {
                        "name": "Bad_Name",
                        "action": "create",
                        "skill_md": "x",
                        "purpose_md": "y",
                    }
                )
                assert bad.status == SpellStatus.ERROR
            finally:
                if agent_skills.exists():
                    shutil.rmtree(agent_skills)

    @pytest.mark.asyncio
    async def test_export_skill_plugin(self, skill_evolution_rune_loaded, tmp_path):
        from pathlib import Path

        agent_skills = (
            Path.home() / ".agents" / ".mvgeos" / "coding_mvge" / "skills" / "export-me"
        )
        agent_skills.mkdir(parents=True, exist_ok=True)
        (agent_skills / "SKILL.md").write_text(
            "---\nname: export-me\ndescription: export test skill\n---\n\n# Export\n",
            encoding="utf-8",
        )
        try:
            spells = {
                s.name: s
                for s in skill_evolution_rune_loaded.get_all_registered_spells()
            }
            spell = spells["skill_evolution_export"]
            result = await spell.execute(
                spell_cast_id="t5",
                params={
                    "skill_names": ["export-me"],
                    "output_dir": str(tmp_path),
                    "plugin_name": "test-plugin",
                },
                signal=None,
                on_update=None,
            )
            assert "plugin_path" in result
            assert (Path(result["plugin_path"]) / "plugin.json").exists()
            assert (
                Path(result["plugin_path"]) / "skills" / "export-me" / "SKILL.md"
            ).exists()
        finally:
            import shutil

            if agent_skills.exists():
                shutil.rmtree(agent_skills)

    @pytest.mark.asyncio
    async def test_rune_command_handlers(self, skill_evolution_rune_loaded):
        from unittest.mock import AsyncMock, patch

        from mvgeos_runes.types import SigilHook

        cmd_map = {c.name: c for c in skill_evolution_rune_loaded.get_commands()}
        # Invoke skill-evolution-consolidate, export, stats
        cmd_map["skill-evolution-consolidate"].handler(None)
        cmd_map["skill-evolution-export"].handler(None)
        cmd_map["skill-evolution-stats"].handler(None)

        # Invoke skill-evolution-propose success path
        sub = getattr(skill_evolution_rune_loaded, "_skill_proposer_subagent", None)
        assert sub is not None
        with patch.object(
            sub,
            "run",
            AsyncMock(
                return_value={"success": True, "action": "create", "name": "foo"}
            ),
        ):
            await cmd_map["skill-evolution-propose"].handler(None)

        # Invoke skill-evolution-propose failure path
        with patch.object(
            sub,
            "run",
            AsyncMock(return_value={"success": False, "error": "fatal error"}),
        ):
            await cmd_map["skill-evolution-propose"].handler(None)

        # Trigger agent start handler
        handlers = skill_evolution_rune_loaded.get_sigil_handlers(SigilHook.AGENT_START)
        for h in handlers:
            await h(None)

    @pytest.mark.asyncio
    async def test_set_llm_client_and_subagent_run(self, skill_evolution_rune_loaded):
        from unittest.mock import AsyncMock, patch

        from coding_mvge.runes.skill_evolution.rune_factory import set_llm_client

        mock_complete_fn = AsyncMock()
        set_llm_client(
            skill_evolution_rune_loaded, mock_complete_fn, model="test/model"
        )
        assert (
            skill_evolution_rune_loaded._experience_consolidator.complete_fn
            is mock_complete_fn
        )
        assert (
            skill_evolution_rune_loaded._experience_consolidator.llm_model
            == "test/model"
        )
        assert (
            skill_evolution_rune_loaded._skill_proposer_subagent.complete_fn
            is mock_complete_fn
        )
        assert (
            skill_evolution_rune_loaded._skill_proposer_subagent.llm_model
            == "test/model"
        )

        # Fallback when runner lacks attributes
        set_llm_client(object(), mock_complete_fn)

        # Subagent runner run method
        with patch(
            "coding_mvge.runes.skill_evolution.rune_factory.run_proposer",
            AsyncMock(return_value={"success": True}),
        ):
            sub = skill_evolution_rune_loaded._skill_proposer_subagent
            res = await sub.run(auto_apply=False)
            assert res == {"success": True}

    def test_rune_partitions_evolution_by_workspace(self, runner, tmp_path):
        from coding_mvge.runes.skill_evolution import rune_factory

        ws = tmp_path / "my_project"
        ws.mkdir()
        (ws / ".git").mkdir()

        runner.bind_context(
            RuneContext(
                cwd=str(ws), mode="test", agent_name="coding_mvge", api_key="test"
            )
        )
        api = runner.create_api("skill_evolution_ws")
        rune_factory(api)

        store = getattr(runner, "_skill_evolution_store", None)
        assert store is not None
        assert "workspaces" in str(store.evolution_dir)
        assert "my_project" in str(store.evolution_dir)

    def test_rune_standalone_no_workspace(self, runner):
        from coding_mvge.runes.skill_evolution import rune_factory

        runner.bind_context(
            RuneContext(cwd="", mode="test", agent_name="coding_mvge", api_key="test")
        )
        api = runner.create_api("skill_evolution_standalone")
        rune_factory(api)

        store = getattr(runner, "_skill_evolution_store", None)
        assert store is not None
        assert "workspaces" not in str(store.evolution_dir)
