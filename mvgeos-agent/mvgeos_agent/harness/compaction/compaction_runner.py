"""Decides when to compact a Mana Pool and carries it out.

The pure measuring and splitting live in `compaction`. This module owns the
side effects: calling a Realm for the summary, emitting lifecycle events, and
recording the compaction on the Tome.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mvgeos_provider.base import Realm
from mvgeos_provider.retry import DEFAULT_RETRY_POLICY, RetryPolicy, retry_invocation
from mvgeos_provider.types import ChannelConfig, Model

if TYPE_CHECKING:
    from mvgeos_agent.agent_session import MvgeTome
    from mvgeos_agent.loop import EmitSink

from mvgeos_agent.harness.compaction.compaction import (
    DEFAULT_COMPACTION_SETTINGS,
    CompactionSettings,
    estimate_context_mana,
    generate_summary,
    prepare_compaction,
    should_compact,
)
from mvgeos_agent.types import (
    ContentType,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    SummonerRequest,
)

logger = logging.getLogger(__name__)

_SUMMARY_PREFIX = "Summary of earlier conversation:\n\n"


class CompactionRunner:
    """Compacts a transcript once it crowds the Mana Pool."""

    def __init__(
        self,
        realm: Realm,
        model: Model,
        emit: EmitSink,
        settings: CompactionSettings = DEFAULT_COMPACTION_SETTINGS,
        tome: MvgeTome | None = None,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> None:
        self._realm = realm
        self._model = model
        self._emit = emit
        self._settings = settings
        self._tome = tome
        self._retry_policy = retry_policy
        self._previous_summary: str | None = None

    async def maybe_compact(
        self, invocations: list[MvgeInvocation]
    ) -> list[MvgeInvocation] | None:
        """Compact if the Mana Pool is crowded, else return None.

        Returns the replacement transcript on success. On any failure it
        returns None and the run continues uncompacted: compaction is a
        recovery mechanism and must not become a new failure mode.
        """
        if not self._settings.enabled:
            return None

        context_mana = estimate_context_mana(invocations).mana
        if not should_compact(context_mana, self._model.context_window, self._settings):
            return None

        prepared = prepare_compaction(
            invocations, self._settings, self._previous_summary
        )
        if prepared is None:
            return None

        await self._emit(
            MvgeEvent(
                type=MvgeEventType.COMPACTION_START,
                data={
                    "mana_before": prepared.mana_before,
                    "mana_pool": self._model.context_window,
                },
            )
        )

        summary = await generate_summary(
            prepared.to_summarize, self._summarize, prepared.previous_summary
        )
        if summary is None:
            await self._emit(
                MvgeEvent(
                    type=MvgeEventType.COMPACTION_END,
                    data={"error": "Summarization failed"},
                )
            )
            return None

        replacement: list[MvgeInvocation] = [
            SummonerRequest(role="user", content=f"{_SUMMARY_PREFIX}{summary}"),
            *prepared.retained_tail,
        ]
        self._previous_summary = summary

        self._record(summary, prepared.mana_before, prepared.retained_tail)

        await self._emit(
            MvgeEvent(
                type=MvgeEventType.COMPACTION_END,
                data={
                    "mana_before": prepared.mana_before,
                    "mana_after": estimate_context_mana(replacement).mana,
                    "summarized": len(prepared.to_summarize),
                    "retained": len(prepared.retained_tail),
                },
            )
        )
        return replacement

    async def _summarize(self, messages: list[dict[str, str]]) -> str:
        """Ask the Realm for a summary. Spells are deliberately not offered."""
        config = ChannelConfig(
            model=self._model,
            temperature=0.3,
            max_tokens=self._model.max_tokens,
        )

        async def produce() -> object:
            return await self._realm.complete(self._model, messages, config)

        response = await retry_invocation(produce, self._retry_policy)  # type: ignore[arg-type]

        if response.error_message or response.invocation is None:
            raise RuntimeError(response.error_message or "Realm returned no summary")

        return "".join(
            block.get("text", "")
            for block in response.invocation.content or []
            if block.get("type") == ContentType.TEXT
        )

    def _record(
        self,
        summary: str,
        mana_before: int,
        retained_tail: list[MvgeInvocation],
    ) -> None:
        if self._tome is None:
            return
        try:
            self._tome.record_compaction(
                summary=summary,
                mana_before=mana_before,
                retained_tail=retained_tail,
            )
        except Exception:
            logger.exception("Failed to record compaction on the Tome")


__all__ = ["CompactionRunner"]
