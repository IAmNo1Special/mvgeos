from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from coding_mvge.runes.skill_evolution.consolidator.consolidator import (
    ExperienceConsolidator,
)
from coding_mvge.runes.skill_evolution.consolidator.harvester import ExperienceHarvester
from coding_mvge.runes.skill_evolution.queries import SkillEvolutionQueries
from coding_mvge.runes.skill_evolution.store import SkillEvolutionStore


@pytest.fixture
def tmp_dirs():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        store = SkillEvolutionStore(td / "skill_evolution")
        store.bind_raw_experience(td / "raw_experience")
        qs = SkillEvolutionQueries(store)
        hv = ExperienceHarvester(max_buffer_size=50, persist_path=td / "buf.json")
        yield store, qs, hv


class TestExperienceHarvester:
    def test_harvest_and_persist_raw(self, tmp_dirs):
        _, _, hv = tmp_dirs
        inv = MagicMock()
        inv.role = "assistant"
        inv.id = "inv_1"
        inv.turn = 1
        inv.prompt = "p"
        inv.content = "r"
        inv.tool_calls = [{"function": {"name": "bash"}}]
        inv.error = None
        inv.mana_used = 10
        hv.harvest(inv)
        assert len(hv.buffer) == 1
        assert hv.buffer[0].spells_used == ["bash"]

    def test_harvest_with_spell_cast_content_blocks(self, tmp_dirs):
        _, _, hv = tmp_dirs
        inv = MagicMock()
        inv.role = "assistant"
        inv.id = "inv_spell_cast"
        inv.turn = 1
        inv.prompt = "run something"
        inv.content = [
            {"type": "text", "text": "Casting spell..."},
            {
                "type": "spell_cast",
                "spell_cast": {"id": "c1", "name": "read_file", "arguments": {}},
            },
        ]
        inv.tool_calls = []
        inv.error = None
        inv.mana_used = 15
        hv.harvest(inv)
        assert len(hv.buffer) == 1
        assert hv.buffer[0].spells_used == ["read_file"]

    def test_ignore_non_assistant(self, tmp_dirs):
        _, _, hv = tmp_dirs
        inv = MagicMock()
        inv.role = "user"
        inv.content = "hi"
        hv.harvest(inv)
        assert len(hv.buffer) == 0

    def test_harvest_with_error(self, tmp_dirs):
        _, _, hv = tmp_dirs
        inv = MagicMock()
        inv.role = "assistant"
        inv.id = "inv_err"
        inv.turn = 1
        inv.content = ""
        inv.tool_calls = []
        inv.error = "Test failure"
        hv.harvest(inv)
        assert hv.buffer[0].success is False
        assert hv.buffer[0].error == "Test failure"

    def test_harvest_empty_content_and_no_spells(self, tmp_dirs):
        _, _, hv = tmp_dirs
        inv = MagicMock()
        inv.role = "assistant"
        inv.id = "inv_empty"
        inv.turn = 1
        inv.content = ""
        inv.tool_calls = []
        inv.error = None
        hv.harvest(inv)
        assert hv.buffer[0].success is False
        assert hv.buffer[0].error == "Empty response"

    @pytest.mark.asyncio
    async def test_harvester_clear_and_persist(self, tmp_dirs, tmp_path):
        _, _, hv = tmp_dirs
        for i in range(4):
            inv = MagicMock(
                role="assistant",
                id=f"i_{i}",
                turn=i,
                prompt="p",
                content="c",
                tool_calls=[],
                error=None,
                mana_used=5,
            )
            hv.harvest(inv)
        assert len(hv.get_staged_traces(max_traces=2)) == 2
        hv.clear_staged(keep_last=2)
        assert len(hv.buffer) == 2

        # persist_to_raw_experience
        await hv.persist_to_raw_experience(tmp_path / "raw", turn=1)
        assert (tmp_path / "raw" / "iter_1" / "i_2.json").exists()

        # persist_buffer & load_buffer
        await hv.persist_buffer()
        hv_new = ExperienceHarvester(max_buffer_size=50, persist_path=hv.persist_path)
        await hv_new.load_buffer()
        assert len(hv_new.buffer) == 2


class TestExperienceConsolidator:
    def test_should_consolidate(self, tmp_dirs):
        store, qs, hv = tmp_dirs
        ec = ExperienceConsolidator(
            store=store,
            queries=qs,
            harvester=hv,
            batch_size=3,
            interval_turns=2,
        )
        for i in range(3):
            inv = MagicMock()
            inv.role = "assistant"
            inv.id = f"inv_{i}"
            inv.turn = i
            inv.prompt = "p"
            inv.content = "r"
            inv.tool_calls = []
            inv.error = None
            inv.mana_used = 10
            hv.harvest(inv)
        assert ec.should_consolidate(5) is True

    @pytest.mark.asyncio
    async def test_consolidate_no_complete_fn_raises(self, tmp_dirs):
        store, qs, hv = tmp_dirs
        ec = ExperienceConsolidator(
            store=store,
            queries=qs,
            harvester=hv,
            batch_size=2,
            interval_turns=2,
        )
        inv = MagicMock()
        inv.role = "assistant"
        inv.id = "inv_1"
        inv.turn = 1
        inv.prompt = "p"
        inv.content = "r"
        inv.tool_calls = []
        inv.error = None
        inv.mana_used = 10
        hv.harvest(inv)
        with pytest.raises(RuntimeError):
            await ec.consolidate_batch(current_turn=5, force=True)

    @pytest.mark.asyncio
    async def test_consolidate_with_complete_fn(self, tmp_dirs):
        store, qs, hv = tmp_dirs
        ec = ExperienceConsolidator(
            store=store,
            queries=qs,
            harvester=hv,
            batch_size=2,
            interval_turns=2,
        )
        for i in range(2):
            inv = MagicMock()
            inv.role = "assistant"
            inv.id = f"inv_{i}"
            inv.turn = i
            inv.prompt = "p"
            inv.content = "r"
            inv.tool_calls = []
            inv.error = None
            inv.mana_used = 10
            hv.harvest(inv)

        async def fake_complete(messages, signal=None):
            return json.dumps(
                {
                    "create_patterns": [
                        {
                            "name": "test-pattern.md",
                            "content": "# Test\ncontent",
                        }
                    ],
                    "update_patterns": [],
                    "update_index": (
                        "# Skill Evolution Index\n"
                        "- [Test](patterns/test-pattern.md): Test"
                    ),
                    "append_log": "ok",
                }
            )

        res = await ec.consolidate_batch(
            current_turn=5, force=True, complete_fn=fake_complete
        )
        assert res is not None
        assert res.entries_created == 1
        assert (store.patterns_dir / "test-pattern.md").exists()

    @pytest.mark.asyncio
    async def test_consolidate_batch_force_false_no_complete_fn_returns_none(
        self, tmp_dirs
    ):
        store, qs, hv = tmp_dirs
        ec = ExperienceConsolidator(
            store=store,
            queries=qs,
            harvester=hv,
            batch_size=1,
            interval_turns=1,
        )
        inv = MagicMock()
        inv.role = "assistant"
        inv.id = "inv_1"
        inv.turn = 1
        inv.prompt = "p"
        inv.content = "r"
        inv.tool_calls = []
        inv.error = None
        inv.mana_used = 10
        hv.harvest(inv)

        # When force=False, should return None rather than raising RuntimeError
        res = await ec.consolidate_batch(current_turn=1, force=False)
        assert res is None

    @pytest.mark.asyncio
    async def test_consolidate_batch_resolves_complete_fn_from_api_key(self, tmp_dirs):
        store, qs, hv = tmp_dirs
        ec = ExperienceConsolidator(
            store=store,
            queries=qs,
            harvester=hv,
            batch_size=1,
            interval_turns=1,
            api_key="test-api-key",
        )
        fn = ec._get_complete_fn()
        assert fn is not None
