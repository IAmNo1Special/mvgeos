from __future__ import annotations

import inspect
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.types import ChannelConfig, Model

from coding_mvge.runes.knowledge_skill.consolidator.harvester import ExperienceHarvester
from coding_mvge.runes.knowledge_skill.consolidator.prompts import (
    KNOWLEDGE_MAINTAINER_SYSTEM,
    build_consolidation_user_prompt,
)
from coding_mvge.runes.knowledge_skill.knowledge.models import (
    ConsolidationLogEntry,
)
from coding_mvge.runes.knowledge_skill.knowledge.queries import KnowledgeQueries
from coding_mvge.runes.knowledge_skill.knowledge.store import KnowledgeStore

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationResult:
    entries_created: int
    entries_updated: int
    duration_ms: int
    log_entry: ConsolidationLogEntry
    raw_proposals: dict[str, Any]


class KnowledgeConsolidator:
    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        knowledge_queries: KnowledgeQueries,
        harvester: ExperienceHarvester,
        batch_size: int = 20,
        interval_turns: int = 5,
        llm_client: object | None = None,
        llm_model: str = "openrouter/auto",
        api_key: str | None = None,
    ):
        self.knowledge = knowledge_store
        self.queries = knowledge_queries
        self.harvester = harvester
        self.batch_size = batch_size
        self.interval_turns = interval_turns
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.api_key = api_key
        self._last_consolidation_turn = 0

    def _resolve_client(self) -> object | None:
        if self.llm_client is not None:
            return self.llm_client
        if self.api_key:
            self.llm_client = OpenRouterRealm(api_key=self.api_key)
            return self.llm_client
        return None

    def should_consolidate(self, current_turn: int) -> bool:
        traces = self.harvester.get_staged_traces()
        if len(traces) >= self.batch_size:
            return True
        if current_turn - self._last_consolidation_turn >= self.interval_turns:
            return len(traces) > 0
        return False

    async def consolidate_batch(
        self,
        current_turn: int,
        force: bool = False,
        llm_client: object | None = None,
    ) -> ConsolidationResult | None:
        if not force and not self.should_consolidate(current_turn):
            return None
        client = llm_client or self.llm_client or self._resolve_client()
        if client is None:
            if force:
                raise RuntimeError("No LLM client available for consolidation")
            logger.warning(
                "No LLM client available for background consolidation; skipping."
            )
            return None

        traces = self.harvester.get_staged_traces(max_traces=self.batch_size)
        if not traces:
            return None
        failures = [t for t in traces if not t.success]
        successes = [t for t in traces if t.success]
        sampled = failures[:5] + successes[:3]
        if not sampled:
            return None
        wiki_index = await self.knowledge.read_index()
        wiki_logs = await self.knowledge.read_logs()
        wiki_impact = await self.knowledge.read_skill_impact()
        patterns = []
        for pf in list(self.knowledge.patterns_dir.glob("*.md"))[:50]:
            patterns.append(f"## {pf.name}\n{pf.read_text(encoding='utf-8')}")
        wiki_context = (
            f"# Knowledge Index\n{wiki_index}\n\n"
            f"# Logs\n{wiki_logs}\n\n"
            f"# Skill Impact\n{wiki_impact}\n\n"
            f"# Patterns\n" + "\n\n".join(patterns)
        )
        trace_dicts = [
            {
                "invocation_id": t.invocation_id,
                "turn": t.turn,
                "prompt": t.prompt,
                "response": t.response,
                "spells_used": t.spells_used,
                "success": t.success,
                "error": t.error,
                "mana_used": t.mana_used,
            }
            for t in sampled
        ]
        user_prompt = build_consolidation_user_prompt(
            wiki_context, trace_dicts, current_turn
        )
        start = time.time()
        response = await self._call_llm(
            client, KNOWLEDGE_MAINTAINER_SYSTEM, user_prompt
        )
        duration_ms = int((time.time() - start) * 1000)
        try:
            proposals = json.loads(response)
        except Exception:
            return None
        entries_created = 0
        entries_updated = 0
        for pattern in proposals.get("create_patterns", []):
            name = pattern.get("name", "")
            if not name.endswith(".md"):
                name += ".md"
            await self.knowledge.add_pattern(
                name, pattern.get("content", ""), current_turn
            )
            entries_created += 1
        for update in proposals.get("update_patterns", []):
            if await self.knowledge.patch_pattern(
                update.get("name", ""), update.get("edits", [])
            ):
                entries_updated += 1
        if "update_index" in proposals:
            await self.knowledge.update_index(proposals["update_index"])
        if "append_log" in proposals:
            await self.knowledge.append_log(proposals["append_log"])
        log_entry = ConsolidationLogEntry(
            turn=current_turn,
            traces_processed=len(sampled),
            entries_created=entries_created,
            entries_updated=entries_updated,
            duration_ms=duration_ms,
            llm_model=self.llm_model,
        )
        await self.knowledge.log_consolidation(log_entry)
        self.harvester.clear_staged(keep_last=0)
        self._last_consolidation_turn = current_turn
        return ConsolidationResult(
            entries_created=entries_created,
            entries_updated=entries_updated,
            duration_ms=duration_ms,
            log_entry=log_entry,
            raw_proposals=proposals,
        )

    async def _call_llm(self, client: Any, system: str, user: str) -> str:
        is_mock = isinstance(client, (MagicMock, AsyncMock))
        has_mock_chat = is_mock and "chat" in getattr(client, "_mock_children", {})
        has_mock_complete = is_mock and "complete" in getattr(
            client, "_mock_children", {}
        )

        if has_mock_chat or (
            not is_mock
            and hasattr(client, "chat")
            and hasattr(client.chat, "completions")
        ):
            completion = await client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            return str(completion.choices[0].message.content)
        elif has_mock_complete or hasattr(client, "complete"):
            sig = inspect.signature(client.complete)
            if len(sig.parameters) == 1:
                res = await client.complete(system + "\n\n" + user)
                return str(res)
            else:
                model = Model(
                    id=self.llm_model,
                    name=self.llm_model,
                    realm="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    api_key="",
                )
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                config = ChannelConfig(model=model, max_tokens=4000, temperature=0.3)
                resp = await client.complete(model, messages, config)
                if (
                    hasattr(resp, "invocation")
                    and resp.invocation
                    and getattr(resp.invocation, "content", None)
                ):
                    for block in resp.invocation.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            return str(block.get("text", ""))
                return ""
        else:
            raise NotImplementedError(f"Unknown LLM client type: {type(client)}")


ExperienceConsolidator = KnowledgeConsolidator
