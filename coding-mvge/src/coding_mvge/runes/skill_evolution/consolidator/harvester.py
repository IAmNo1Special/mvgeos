from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mvgeos_core.invocations import MvgeInvocation


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
    """Harvests raw experience from invocations without LLM calls.

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
        if invocation.role != "assistant":
            return

        spells_used: list[str] = []
        spell_results: list[dict[str, Any]] = []

        if hasattr(invocation, "tool_calls") and invocation.tool_calls:
            for tc in invocation.tool_calls:
                spells_used.append(tc.get("function", {}).get("name", "unknown"))

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

    async def persist_buffer(self) -> None:
        """Save in-memory buffer to disk."""
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "id": t.invocation_id,
                "turn": t.turn,
                "prompt": t.prompt,
                "response": t.response,
                "spells_used": t.spells_used,
                "success": t.success,
                "error": t.error,
                "mana_used": t.mana_used,
            }
            for t in self.buffer
        ]
        self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def load_buffer(self) -> None:
        """Load previously persisted buffer from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            for d in data:
                self.buffer.append(
                    RawTrace(
                        invocation_id=d["id"],
                        turn=d["turn"],
                        prompt=d["prompt"],
                        response=d["response"],
                        spells_used=d.get("spells_used", []),
                        spell_results=[],
                        success=d.get("success", True),
                        error=d.get("error"),
                        mana_used=d.get("mana_used", 0),
                    )
                )
        except Exception:
            pass

    async def persist_to_raw_experience(
        self,
        raw_experience_dir: Path,
        current_turn: int = 0,
        *,
        turn: int | None = None,
    ) -> None:
        """Append immutable execution traces per WikiSkill §3.1."""
        effective_turn = turn if turn is not None else current_turn
        iter_dir = raw_experience_dir / f"iter_{effective_turn}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        traces_dir = raw_experience_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        for t in self.buffer:
            data = json.dumps(
                {
                    "invocation_id": t.invocation_id,
                    "turn": t.turn,
                    "prompt": t.prompt,
                    "response": t.response,
                    "spells_used": t.spells_used,
                    "success": t.success,
                    "error": t.error,
                    "mana_used": t.mana_used,
                },
                indent=2,
            )
            out_iter = iter_dir / f"{t.invocation_id}.json"
            if not out_iter.exists():
                out_iter.write_text(data, encoding="utf-8")
            out_traces = traces_dir / f"{t.invocation_id}.json"
            if not out_traces.exists():
                out_traces.write_text(data, encoding="utf-8")

    def get_stats(self) -> dict[str, Any]:
        return {
            "buffered_traces": len(self.buffer),
            "total_harvested": self._total_harvested,
            "failed_traces": sum(1 for t in self.buffer if not t.success),
            "success_traces": sum(1 for t in self.buffer if t.success),
        }
