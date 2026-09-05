from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from coding_mvge.runes.knowledge_skill.knowledge.queries import KnowledgeQueries
from coding_mvge.runes.knowledge_skill.knowledge.store import KnowledgeStore


@pytest.fixture
def tmp_knowledge():
    with tempfile.TemporaryDirectory() as td:
        ks = KnowledgeStore(Path(td) / "knowledge")
        yield ks


def _pattern_md(
    name: str = "test-pattern.md", content: str = "pattern content refactor"
) -> tuple[str, str]:
    return name, f"# {name}\n\n{content}\n"


class TestKnowledgeStore:
    @pytest.mark.asyncio
    async def test_add_and_list_pattern(self, tmp_knowledge):
        await tmp_knowledge.add_pattern(
            "refactor-extract.md", "# Extract\ncontent here", turn=1
        )
        patterns = await tmp_knowledge.list_patterns()
        assert any(p.name == "refactor-extract.md" for p in patterns)
        assert (tmp_knowledge.patterns_dir / "refactor-extract.md").exists()

    @pytest.mark.asyncio
    async def test_patch_append_replace_insert(self, tmp_knowledge):
        await tmp_knowledge.add_pattern("p.md", "hello world", turn=1)
        ok = await tmp_knowledge.patch_pattern(
            "p.md", [{"op": "append", "content": " appended"}]
        )
        assert ok
        assert "appended" in (tmp_knowledge.patterns_dir / "p.md").read_text(
            encoding="utf-8"
        )
        # replace exact
        ok = await tmp_knowledge.patch_pattern(
            "p.md", [{"op": "replace", "target": "hello", "content": "hi"}]
        )
        assert ok
        txt = (tmp_knowledge.patterns_dir / "p.md").read_text(encoding="utf-8")
        assert txt.startswith("hi")
        # insert_after
        ok = await tmp_knowledge.patch_pattern(
            "p.md", [{"op": "insert_after", "target": "hi", "content": " there"}]
        )
        assert ok
        assert "hi there" in (tmp_knowledge.patterns_dir / "p.md").read_text(
            encoding="utf-8"
        )
        # missing target fails
        ok = await tmp_knowledge.patch_pattern(
            "p.md", [{"op": "replace", "target": "MISSING_XYZ", "content": "x"}]
        )
        assert not ok

    @pytest.mark.asyncio
    async def test_index_logs_skill_impact(self, tmp_knowledge):
        await tmp_knowledge.update_index(
            "# Knowledge Index\n- [p](patterns/p.md): desc"
        )
        assert "Knowledge Index" in await tmp_knowledge.read_index()
        await tmp_knowledge.append_log("iteration 1: found 1 pattern")
        assert "iteration 1" in await tmp_knowledge.read_logs()
        await tmp_knowledge.append_skill_impact(
            {"name": "my-skill", "action": "create", "turn": 1},
            r_val=0.8,
            accepted=True,
            diff="diff here",
        )
        assert "my-skill" in await tmp_knowledge.read_skill_impact()

    @pytest.mark.asyncio
    async def test_search(self, tmp_knowledge):
        await tmp_knowledge.add_pattern(
            "a.md", "extract method refactor long functions", turn=1
        )
        await tmp_knowledge.add_pattern("b.md", "async testing pytest-asyncio", turn=2)
        hits = await tmp_knowledge.search("refactor", limit=10)
        assert len(hits) == 1
        assert hits[0].name == "a.md"
        hits = await tmp_knowledge.search("pytest", limit=10)
        assert any(h.name == "b.md" for h in hits)


class TestKnowledgeQueries:
    @pytest.mark.asyncio
    async def test_search_and_stats(self, tmp_knowledge):
        await tmp_knowledge.add_pattern(
            "how-to-refactor.md", "refactor long functions via extract", turn=1
        )
        await tmp_knowledge.add_pattern("async-test.md", "testing async code", turn=2)
        qs = KnowledgeQueries(tmp_knowledge)
        hits = await qs.find_relevant_patterns("refactor", limit=5)
        assert len(hits) == 1
        assert hits[0].name == "how-to-refactor.md"
        hits = await qs.get_patterns_for_skill("refactor", "extract method", limit=5)
        assert any("refactor" in h.name for h in hits)
        stats = await qs.get_wiki_stats()
        assert stats["total_entries"] == 2
