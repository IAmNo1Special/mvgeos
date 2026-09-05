from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from coding_mvge.runes.knowledge_skill.consolidator.consolidator import (
    KnowledgeConsolidator,
)
from coding_mvge.runes.knowledge_skill.consolidator.harvester import ExperienceHarvester
from coding_mvge.runes.knowledge_skill.knowledge.queries import KnowledgeQueries
from coding_mvge.runes.knowledge_skill.knowledge.store import KnowledgeStore


@pytest.fixture
def tmp_dirs():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ks = KnowledgeStore(td / "knowledge")
        ks.bind_raw_knowledge(td / "raw_knowledge")
        qs = KnowledgeQueries(ks)
        hv = ExperienceHarvester(max_buffer_size=50, persist_path=td / "buf.json")
        yield ks, qs, hv


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

        # persist_to_raw_knowledge
        await hv.persist_to_raw_knowledge(tmp_path / "raw", turn=1)
        assert (tmp_path / "raw" / "iter_1" / "i_2.json").exists()

        # persist_buffer & load_buffer
        await hv.persist_buffer()
        hv_new = ExperienceHarvester(max_buffer_size=50, persist_path=hv.persist_path)
        await hv_new.load_buffer()
        assert len(hv_new.buffer) == 2


class TestKnowledgeConsolidator:
    def test_should_consolidate(self, tmp_dirs):
        ks, qs, hv = tmp_dirs
        kc = KnowledgeConsolidator(
            knowledge_store=ks,
            knowledge_queries=qs,
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
        assert kc.should_consolidate(5) is True

    @pytest.mark.asyncio
    async def test_consolidate_no_llm_raises(self, tmp_dirs):
        ks, qs, hv = tmp_dirs
        kc = KnowledgeConsolidator(
            knowledge_store=ks,
            knowledge_queries=qs,
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
            await kc.consolidate_batch(current_turn=5, force=True)

    @pytest.mark.asyncio
    async def test_consolidate_with_mock(self, tmp_dirs):
        import json

        ks, qs, hv = tmp_dirs
        kc = KnowledgeConsolidator(
            knowledge_store=ks,
            knowledge_queries=qs,
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
        mock = AsyncMock()
        mock.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "create_patterns": [
                                        {
                                            "name": "test-pattern.md",
                                            "content": "# Test\ncontent",
                                        }
                                    ],
                                    "update_patterns": [],
                                    "update_index": (
                                        "# Knowledge Index\n"
                                        "- [Test](patterns/test-pattern.md): Test"
                                    ),
                                    "append_log": "ok",
                                }
                            )
                        )
                    )
                ]
            )
        )
        res = await kc.consolidate_batch(current_turn=5, force=True, llm_client=mock)
        assert res is not None
        assert res.entries_created == 1
        assert (ks.patterns_dir / "test-pattern.md").exists()

    @pytest.mark.asyncio
    async def test_consolidate_batch_force_false_no_client_returns_none(self, tmp_dirs):
        ks, qs, hv = tmp_dirs
        kc = KnowledgeConsolidator(
            knowledge_store=ks,
            knowledge_queries=qs,
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
        res = await kc.consolidate_batch(current_turn=1, force=False)
        assert res is None

    @pytest.mark.asyncio
    async def test_consolidate_batch_resolves_default_client_from_api_key(
        self, tmp_dirs
    ):
        ks, qs, hv = tmp_dirs
        kc = KnowledgeConsolidator(
            knowledge_store=ks,
            knowledge_queries=qs,
            harvester=hv,
            batch_size=1,
            interval_turns=1,
            api_key="test-api-key",
        )
        resolved = kc._resolve_client()
        assert resolved is not None

    @pytest.mark.asyncio
    async def test_call_llm_with_realm_complete(self, tmp_dirs):
        ks, qs, hv = tmp_dirs
        kc = KnowledgeConsolidator(
            knowledge_store=ks,
            knowledge_queries=qs,
            harvester=hv,
        )
        mock_realm = MagicMock()
        mock_response = MagicMock()
        mock_response.invocation.content = [{"type": "text", "text": '{"ok": true}'}]
        mock_realm.complete = AsyncMock(return_value=mock_response)

        text = await kc._call_llm(mock_realm, "system prompt", "user prompt")
        assert text == '{"ok": true}'
        mock_realm.complete.assert_awaited_once()
