from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mvgeos_core.abort import AbortSignal
from mvgeos_core.channel import (
    ChannelConfig,
    Model,
)
from mvgeos_provider.base import NoRealmRegisteredError
from mvgeos_provider.registry import get_registry

from coding_mvge.runes.skill_evolution.consolidator.harvester import ExperienceHarvester
from coding_mvge.runes.skill_evolution.consolidator.prompts import (
    SKILL_EVOLUTION_MAINTAINER_SYSTEM,
    build_consolidation_user_prompt,
)
from coding_mvge.runes.skill_evolution.models import ConsolidationLogEntry
from coding_mvge.runes.skill_evolution.queries import SkillEvolutionQueries
from coding_mvge.runes.skill_evolution.store import SkillEvolutionStore

logger = logging.getLogger(__name__)

CompleteFn = Callable[[list[dict[str, str]], AbortSignal | None], Awaitable[str]]


def make_realm_complete_fn(realm: Any, model_id: str = "openrouter/auto") -> CompleteFn:
    """Create a CompleteFn adapter wrapping Realm.complete()."""
    model = Model(
        id=model_id,
        name=model_id,
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
    )

    async def _complete(
        messages: list[dict[str, str]], signal: AbortSignal | None = None
    ) -> str:
        config = ChannelConfig(
            model=model,
            temperature=0.3,
            max_tokens=4000,
        )
        resp = await realm.complete(model, messages, config, signal)
        return resp.content if hasattr(resp, "content") else str(resp)

    return _complete


@dataclass
class ConsolidationResult:
    entries_created: int
    entries_updated: int
    duration_ms: int
    log_entry: ConsolidationLogEntry
    raw_proposals: dict[str, Any]


class ExperienceConsolidator:
    """Deep module for consolidating raw execution traces into persistent patterns.

    Consumes raw traces from ExperienceHarvester, generates incremental patch proposals
    via the CompleteFn seam, and applies updates directly to SkillEvolutionStore.
    """

    def __init__(
        self,
        store: SkillEvolutionStore | None = None,
        queries: SkillEvolutionQueries | None = None,
        harvester: ExperienceHarvester | None = None,
        batch_size: int = 20,
        interval_turns: int = 5,
        complete_fn: CompleteFn | None = None,
        api_key: str | None = None,
        llm_model: str = "openrouter/auto",
        **kwargs: Any,
    ):
        actual_store = (
            store
            or kwargs.get("skill_evolution_store")
            or kwargs.get("knowledge_store")
        )
        if actual_store is None:
            raise ValueError("store must be provided to ExperienceConsolidator")
        actual_queries = (
            queries
            or kwargs.get("skill_evolution_queries")
            or kwargs.get("knowledge_queries")
        )
        if actual_queries is None:
            raise ValueError("queries must be provided to ExperienceConsolidator")
        actual_harvester = harvester or kwargs.get("harvester")
        if actual_harvester is None:
            raise ValueError("harvester must be provided to ExperienceConsolidator")
        self.store = actual_store
        self.queries = actual_queries
        self.harvester = actual_harvester
        self.batch_size = batch_size
        self.interval_turns = interval_turns
        self.complete_fn = complete_fn
        self.api_key = api_key
        self.llm_model = llm_model
        self._last_consolidation_turn = 0

    def should_consolidate(self, current_turn: int) -> bool:
        traces = self.harvester.get_staged_traces()
        if len(traces) >= self.batch_size:
            return True
        if current_turn - self._last_consolidation_turn >= self.interval_turns:
            return len(traces) > 0
        return False

    def _get_complete_fn(self) -> CompleteFn | None:
        if self.complete_fn is not None:
            return self.complete_fn
        if self.api_key:
            try:
                realm = get_registry().create_realm(
                    self.llm_model, api_key=self.api_key
                )
                self.complete_fn = make_realm_complete_fn(realm, self.llm_model)
                return self.complete_fn
            except NoRealmRegisteredError as exc:
                logger.warning("Cannot initialize realm for consolidation: %s", exc)
                return None
        return None

    async def consolidate_batch(
        self,
        current_turn: int,
        force: bool = False,
        complete_fn: CompleteFn | None = None,
        signal: AbortSignal | None = None,
    ) -> ConsolidationResult | None:
        if not force and not self.should_consolidate(current_turn):
            return None

        fn = complete_fn or self._get_complete_fn()
        if fn is None:
            if force:
                raise RuntimeError(
                    "No LLM completion function available for consolidation"
                )
            logger.warning(
                "No LLM completion function available for background consolidation; "
                "skipping."
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

        evolution_index = await self.store.read_index()
        logs = await self.queries.get_recent_consolidation_summary(5)
        skill_impact = await self.store.read_skill_impact()
        patterns = await self.store.list_patterns()
        pattern_texts: list[str] = []
        for p in patterns[:10]:
            pattern_texts.append(f"### {p.name}\n{p.read_text(encoding='utf-8')[:500]}")

        evolution_context = (
            f"# INDEX\n{evolution_index}\n\n"
            f"# RECENT LOGS\n{logs}\n\n"
            f"# SKILL IMPACT\n{skill_impact[:1000]}\n\n"
            f"# EXISTING PATTERNS (Sample)\n{'\n\n'.join(pattern_texts)}"
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
            }
            for t in sampled
        ]

        user_prompt = build_consolidation_user_prompt(
            evolution_context, trace_dicts, current_turn
        )

        messages = [
            {"role": "system", "content": SKILL_EVOLUTION_MAINTAINER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        t0 = time.monotonic()
        raw_response = await fn(messages, signal)
        duration_ms = int((time.monotonic() - t0) * 1000)

        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            proposals = json.loads(cleaned)
        except Exception as exc:
            logger.warning(
                "Failed to parse consolidation LLM response as JSON: %s\nResponse: %s",
                exc,
                raw_response[:200],
            )
            return None

        entries_created = 0
        entries_updated = 0

        for cp in proposals.get("create_patterns", []):
            name = cp.get("name")
            content = cp.get("content")
            if name and content:
                await self.store.add_pattern(name, content, turn=current_turn)
                entries_created += 1

        for up in proposals.get("update_patterns", []):
            name = up.get("name")
            edits = up.get("edits", [])
            if name and edits:
                ok = await self.store.patch_pattern(name, edits)
                if ok:
                    entries_updated += 1

        new_index = proposals.get("update_index")
        if new_index:
            await self.store.update_index(new_index)

        append_log = proposals.get("append_log", f"Consolidated {len(sampled)} traces")
        await self.store.append_log(append_log)
        log_entry = ConsolidationLogEntry(
            turn=current_turn,
            traces_processed=len(sampled),
            entries_created=entries_created,
            entries_updated=entries_updated,
            duration_ms=duration_ms,
            llm_model=self.llm_model,
        )
        await self.store.log_consolidation(log_entry)
        self.harvester.clear_staged(keep_last=0)
        self._last_consolidation_turn = current_turn

        return ConsolidationResult(
            entries_created=entries_created,
            entries_updated=entries_updated,
            duration_ms=duration_ms,
            log_entry=log_entry,
            raw_proposals=proposals,
        )
