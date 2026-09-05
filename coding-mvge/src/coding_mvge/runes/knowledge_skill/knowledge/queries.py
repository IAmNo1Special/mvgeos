from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from coding_mvge.runes.knowledge_skill.knowledge.store import KnowledgeStore


class KnowledgeQueries:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    async def search(self, query: str, limit: int = 10) -> list[Path]:
        res: list[Path] = await self.store.search(query, limit)
        return res

    async def find_relevant_patterns(
        self, query: str, tags: list[str] | None = None, limit: int = 10
    ) -> list[Path]:
        hits: list[Path] = await self.store.search(query, limit * 2)
        return hits[:limit]

    async def get_patterns_for_skill(
        self, skill_name: str, skill_description: str, limit: int = 20
    ) -> list[Path]:
        all_hits: list[Path] = []
        for q in [skill_name, skill_description]:
            hits: list[Path] = await self.store.search(q, limit)
            all_hits.extend(hits)
        seen: set[str] = set()
        uniq: list[Path] = []
        for p in all_hits:
            if str(p) not in seen:
                seen.add(str(p))
                uniq.append(p)
        return uniq[:limit]

    async def get_recent_consolidation_summary(self, limit: int = 5) -> str:
        logs = await self.store.read_logs()
        lines = logs.strip().splitlines()[-limit:]
        return "\n".join(lines) if lines else "No consolidations yet."

    async def get_wiki_stats(self) -> dict[str, Any]:
        meta = self.store.get_metadata()
        patterns = await self.store.list_patterns()
        return {
            "total_entries": len(patterns),
            "total_consolidations": getattr(meta, "total_consolidations", 0),
            "last_consolidation_turn": getattr(meta, "last_consolidation_turn", 0),
            "recent_entries_analyzed": len(patterns),
        }

    async def get_failure_patterns(
        self, since_turn: int | None = None, limit: int = 20
    ) -> list[Path]:
        hits: list[Path] = await self.store.search("failure", limit)
        return hits[:limit]

    async def get_success_patterns(
        self, since_turn: int | None = None, limit: int = 20
    ) -> list[Path]:
        hits: list[Path] = await self.store.search("success", limit)
        return hits[:limit]


WikiQueries = KnowledgeQueries
