from __future__ import annotations

import dataclasses
import logging
from typing import Any

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntry, TomeMetadata

logger = logging.getLogger(__name__)


def _serialise_invocation(invocation: Any) -> dict[str, Any]:
    """Flatten an Invocation to JSON-safe primitives for the Tome file."""
    if dataclasses.is_dataclass(invocation) and not isinstance(invocation, type):
        return dataclasses.asdict(invocation)
    return {"role": getattr(invocation, "role", "unknown")}


class MvgeTome:
    def __init__(
        self,
        ledger: TomeLedger,
        tome_metadata: TomeMetadata,
        rune_runner: RuneRunner | None = None,
    ) -> None:
        self._ledger = ledger
        self._metadata = tome_metadata
        self._rune_runner = rune_runner
        self._started = False

    @property
    def tome_id(self) -> str:
        return self._metadata.id

    @property
    def tome_file(self) -> str:
        # Return the path to the tome's JSONL file
        return str(self._ledger.tome_file(self._metadata.id))

    @property
    def ledger(self) -> TomeLedger:
        return self._ledger

    @property
    def metadata(self) -> TomeMetadata:
        return self._metadata

    @property
    def active_leaf_id(self) -> str | None:
        return (
            self._ledger.get_leaf_id(self._metadata.id) or self._metadata.active_leaf_id
        )

    def bind_runner(self, runner: RuneRunner) -> None:
        self._rune_runner = runner

    async def start(self, reason: str = "startup") -> None:
        if self._started:
            return
        self._started = True
        await self._safe_emit(
            SigilHook.SESSION_START,
            {
                "reason": reason,
                "tomeId": self._metadata.id,
                "tomeFile": self.tome_file,
            },
        )

    async def shutdown(
        self, reason: str = "quit", target_session_file: str | None = None
    ) -> None:
        if not self._started:
            return
        self._started = False
        data: dict[str, Any] = {
            "reason": reason,
            "tomeId": self._metadata.id,
        }
        if target_session_file is not None:
            data["targetSessionFile"] = target_session_file
        await self._safe_emit(SigilHook.SESSION_SHUTDOWN, data)

    async def before_switch(self, target_file: str) -> dict[str, Any] | None:
        result = await self._safe_emit_first(
            SigilHook.SESSION_BEFORE_SWITCH,
            {
                "targetSessionFile": target_file,
                "tomeId": self._metadata.id,
            },
        )
        if isinstance(result, dict) and result.get("cancel"):
            return {"cancelled": True}
        return {"cancelled": False}

    async def before_fork(self, entry_id: str) -> dict[str, Any] | None:
        result = await self._safe_emit_first(
            SigilHook.SESSION_BEFORE_FORK,
            {
                "entryId": entry_id,
                "tomeId": self._metadata.id,
            },
        )
        if isinstance(result, dict) and result.get("cancel"):
            return {"cancelled": True}
        return {"cancelled": False}

    def record_message(
        self,
        role: str,
        content: Any,
        parent_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> TomeEntry | None:
        if not self._started:
            logger.warning(
                "record_message dropped: tome %s not started",
                self._metadata.id,
            )
            return None
        if parent_id is None:
            parent_id = self.active_leaf_id
        entry = self._ledger.append_message(
            tome_id=self._metadata.id,
            role=role,
            content=content,
            parent_id=parent_id,
            model=model,
            provider=provider,
        )
        self._advance_leaf(entry)
        return entry

    def _advance_leaf(self, entry: TomeEntry | None) -> None:
        """Move the Tome's Leaf to the entry just appended.

        The Leaf marks the current tip of the branch, so it advances on every
        recorded entry. Forking reads it to decide where to branch from.
        """
        if entry is None:
            return
        try:
            self._ledger.append_leaf(self._metadata.id, entry.id)
        except Exception:
            logger.exception(
                "Failed to advance the Leaf for tome %s", self._metadata.id
            )

    def record_compaction(
        self,
        summary: str,
        mana_before: int,
        retained_tail: list[Any],
        first_kept_entry_id: str | None = None,
        parent_id: str | None = None,
    ) -> TomeEntry | None:
        """Record a compaction so the Tome can rebuild context without replaying
        the Invocations the summary replaced."""
        if not self._started:
            logger.warning(
                "record_compaction dropped: tome %s not started",
                self._metadata.id,
            )
            return None
        if parent_id is None:
            parent_id = self.active_leaf_id
        payload: dict[str, Any] = {
            "summary": summary,
            "manaBefore": mana_before,
            "retainedTail": [_serialise_invocation(inv) for inv in retained_tail],
        }
        if first_kept_entry_id is not None:
            payload["firstKeptEntryId"] = first_kept_entry_id
        return self._ledger.append_compaction(
            tome_id=self._metadata.id,
            payload=payload,
            parent_id=parent_id,
        )

    def record_custom(
        self,
        custom_type: str,
        data: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> TomeEntry | None:
        if not self._started:
            logger.warning(
                "record_custom dropped: tome %s not started",
                self._metadata.id,
            )
            return None
        if parent_id is None:
            parent_id = self.active_leaf_id
        return self._ledger.append_custom(
            tome_id=self._metadata.id,
            payload={"type": custom_type, "data": data or {}},
            parent_id=parent_id,
        )

    async def active_leaf_id_async(self) -> str | None:
        return (
            await self._ledger.get_leaf_id_async(self._metadata.id)
            or self._metadata.active_leaf_id
        )

    async def record_message_async(
        self,
        role: str,
        content: Any,
        parent_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> TomeEntry | None:
        if not self._started:
            logger.warning(
                "record_message_async dropped: tome %s not started",
                self._metadata.id,
            )
            return None
        if parent_id is None:
            parent_id = await self.active_leaf_id_async()
        entry = await self._ledger.append_message_async(
            tome_id=self._metadata.id,
            role=role,
            content=content,
            parent_id=parent_id,
            model=model,
            provider=provider,
        )
        await self._advance_leaf_async(entry)
        return entry

    async def _advance_leaf_async(self, entry: TomeEntry | None) -> None:
        """Non-blocking variant of `_advance_leaf`."""
        if entry is None:
            return
        try:
            await self._ledger.append_leaf_async(self._metadata.id, entry.id)
        except Exception:
            logger.exception(
                "Failed to advance the Leaf for tome %s", self._metadata.id
            )

    async def record_compaction_async(
        self,
        summary: str,
        mana_before: int,
        retained_tail: list[Any],
        first_kept_entry_id: str | None = None,
        parent_id: str | None = None,
    ) -> TomeEntry | None:
        if not self._started:
            logger.warning(
                "record_compaction_async dropped: tome %s not started",
                self._metadata.id,
            )
            return None
        if parent_id is None:
            parent_id = await self.active_leaf_id_async()
        payload: dict[str, Any] = {
            "summary": summary,
            "manaBefore": mana_before,
            "retainedTail": [_serialise_invocation(inv) for inv in retained_tail],
        }
        if first_kept_entry_id is not None:
            payload["firstKeptEntryId"] = first_kept_entry_id
        return await self._ledger.append_compaction_async(
            tome_id=self._metadata.id,
            payload=payload,
            parent_id=parent_id,
        )

    async def record_custom_async(
        self,
        custom_type: str,
        data: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> TomeEntry | None:
        if not self._started:
            logger.warning(
                "record_custom_async dropped: tome %s not started",
                self._metadata.id,
            )
            return None
        if parent_id is None:
            parent_id = await self.active_leaf_id_async()
        return await self._ledger.append_custom_async(
            tome_id=self._metadata.id,
            payload={"type": custom_type, "data": data or {}},
            parent_id=parent_id,
        )

    async def _safe_emit(self, hook: SigilHook, data: Any) -> None:
        if self._rune_runner is None:
            return
        try:
            await self._rune_runner.emit_async(hook, data)
        except Exception:
            logger.exception("Failed to emit %s", hook)

    async def _safe_emit_first(self, hook: SigilHook, data: Any) -> Any | None:
        if self._rune_runner is None:
            return None
        try:
            return await self._rune_runner.emit_first(hook, data)
        except Exception:
            logger.exception("Failed to emit %s", hook)
            return None
