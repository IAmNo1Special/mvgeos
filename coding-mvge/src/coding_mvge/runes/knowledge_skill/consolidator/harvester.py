from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]
from mvgeos_agent.types import MvgeInvocation


@dataclass
class RawTrace:
    """Raw invocation trace staged for consolidation."""

    invocation_id: str
    turn: int
    prompt: str
    response: str
    spells_used: list[str]
    spell_results: list[dict[str, Any]]
    success: bool
    error: str | None = None
    mana_used: int = 0


class ExperienceHarvester:
    """
    Harvests raw experience from invocations without LLM calls.
    Stages traces in memory for batch consolidation.
    """

    def __init__(
        self,
        max_buffer_size: int = 100,
        persist_path: Path | None = None,
    ):
        self.buffer: deque[RawTrace] = deque(maxlen=max_buffer_size)
        self.persist_path = persist_path
        self._total_harvested = 0

    def harvest(self, invocation: MvgeInvocation) -> None:
        """Extract raw data from an invocation (no LLM call)."""
        # MvgeInvocation can be SummonerRequest, MvgeResponse, or SpellResultMessage
        # We only care about complete turns with responses
        if invocation.role != "assistant":
            return

        # Extract spell casts and results from the invocation
        spells_used = []
        spell_results: list[dict[str, Any]] = []

        if hasattr(invocation, "tool_calls") and invocation.tool_calls:
            for tc in invocation.tool_calls:
                spells_used.append(tc.get("function", {}).get("name", "unknown"))

        # Determine success (heuristic: no error, has content)
        success = True
        error = None
        if hasattr(invocation, "error") and invocation.error:
            success = False
            error = str(invocation.error)
        elif not invocation.content and not spells_used:
            success = False
            error = "Empty response"

        resp_content = invocation.content
        trace_resp = (
            resp_content if isinstance(resp_content, str) else str(resp_content or "")
        )

        trace = RawTrace(
            invocation_id=getattr(invocation, "id", f"inv_{self._total_harvested}"),
            turn=getattr(invocation, "turn", 0),
            prompt=getattr(invocation, "prompt", "") or "",
            response=trace_resp,
            spells_used=spells_used,
            spell_results=spell_results,
            success=success,
            error=error,
            mana_used=getattr(invocation, "mana_used", 0),
        )

        self.buffer.append(trace)
        self._total_harvested += 1

    def get_staged_traces(self, max_traces: int | None = None) -> list[RawTrace]:
        """Get traces staged for consolidation."""
        traces = list(self.buffer)
        if max_traces:
            traces = traces[-max_traces:]
        return traces

    def clear_staged(self, keep_last: int = 0) -> None:
        """Clear staged traces after consolidation."""
        if keep_last > 0:
            remaining = list(self.buffer)[-keep_last:]
            self.buffer.clear()
            self.buffer.extend(remaining)
        else:
            self.buffer.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "buffer_size": len(self.buffer),
            "total_harvested": self._total_harvested,
            "success_rate": sum(1 for t in self.buffer if t.success) / len(self.buffer)
            if self.buffer
            else 0,
        }

    async def persist_to_raw_knowledge(self, raw_dir: Path, turn: int) -> None:
        """Persist staged traces immutably to raw_knowledge/ per paper §3.1 raw/."""
        raw_path = Path(raw_dir).expanduser().resolve() / f"iter_{turn}"
        raw_path.mkdir(parents=True, exist_ok=True)
        for t in list(self.buffer):
            (raw_path / f"{t.invocation_id}.json").write_text(
                json.dumps(t.__dict__, indent=2), encoding="utf-8"
            )

    async def persist_buffer(self) -> None:
        """Persist buffer to disk for crash recovery."""
        if not self.persist_path:
            return

        data = {
            "traces": [
                {
                    "invocation_id": t.invocation_id,
                    "turn": t.turn,
                    "prompt": t.prompt,
                    "response": t.response,
                    "spells_used": t.spells_used,
                    "spell_results": t.spell_results,
                    "success": t.success,
                    "error": t.error,
                    "mana_used": t.mana_used,
                }
                for t in self.buffer
            ],
            "total_harvested": self._total_harvested,
        }

        async with aiofiles.open(self.persist_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2))

    async def load_buffer(self) -> None:
        """Load buffer from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return

        async with aiofiles.open(self.persist_path, encoding="utf-8") as f:
            data = json.loads(await f.read())

        self._total_harvested = data.get("total_harvested", 0)
        for t in data.get("traces", []):
            self.buffer.append(RawTrace(**t))
