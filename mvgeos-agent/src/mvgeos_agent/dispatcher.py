from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mvgeos_agent.errors import (
    MvgeError,
    SpellNotFoundError,
    SpellTimeoutError,
    to_error,
)
from mvgeos_agent.truncate import (
    MAX_SPELL_RESULT_BYTES,
    format_size,
    truncate_head,
)
from mvgeos_agent.types import (
    AbortError,
    AbortSignal,
    ContentType,
    MvgeEvent,
    MvgeEventType,
    MvgeResponse,
    SpellExecutionMode,
    SpellResult,
    SpellResultMessage,
    StopReason,
)

if TYPE_CHECKING:
    from mvgeos_agent.core_loop import EmitSink, LoopCallbacks, LoopContext

_TRUNCATED_SPELL_CALL = (
    "Spell '{name}' was not cast: the response hit the output Mana limit, so its "
    "arguments may be truncated. Re-issue the spell cast with complete arguments."
)


def _apply_backstop(
    result_text: str, details: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Cap bypassing spell output so one cast cannot poison the Mana Pool.

    Spell-level truncation runs first; this fires only when a spell
    bypassed its own bound. Preserves the spell's original totals.
    """
    if len(result_text.encode("utf-8")) <= MAX_SPELL_RESULT_BYTES:
        return result_text, details
    capped = truncate_head(result_text, max_bytes=MAX_SPELL_RESULT_BYTES)
    existing = details.get("truncation")
    if isinstance(existing, dict):
        merged = dict(existing)
        shown = capped.text.count("\n") + (1 if capped.text else 0)
        try:
            total = int(merged.get("total_lines", capped.total_lines))
        except (TypeError, ValueError):
            total = capped.total_lines
        merged["shown_start"] = total - shown + 1 if shown else None
        merged["shown_end"] = total if shown else None
        merged["backstop_applied"] = True
        details["truncation"] = merged
    else:
        details["truncation"] = {
            "version": 1,
            "truncated": True,
            "strategy": "head",
            "total_lines": capped.total_lines,
            "shown_start": capped.shown_start,
            "shown_end": capped.shown_end,
            "total_bytes": capped.total_bytes,
            "full_output_path": None,
            "backstop_applied": True,
        }
    notice = (
        f"\n\n[Dispatcher backstop: output exceeded "
        f"{format_size(MAX_SPELL_RESULT_BYTES)} limit.]"
    )
    return f"{capped.text}{notice}", details


@dataclass
class BatchResult:
    """The outcome of a batch of spell cast requests."""

    messages: list[SpellResultMessage] = field(default_factory=list)
    terminate: bool = False


class SpellDispatcher:
    """Deep module for executing spell cast batches concurrently or sequentially.

    Encapsulates parallel execution (asyncio.gather), sequential fallback,
    error isolation, sigil hook callbacks, timeout boundaries, and request-order
    preservation behind a single seam.
    """

    async def dispatch_batch(
        self,
        inv: MvgeResponse,
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> BatchResult:
        spell_casts = [
            item["spell_cast"]
            for item in inv.content or []
            if item.get("type") == ContentType.SPELL_CAST
        ]
        if not spell_casts:
            return BatchResult()

        if inv.stop_reason == StopReason.LENGTH:
            return await self._handle_truncated(spell_casts, emit)

        # If any spell in batch requests sequential, run sequentially
        has_sequential = False
        for spell_cast in spell_casts:
            spell_name = spell_cast.get("name")
            spell = context.get_spell(spell_name) if spell_name else None
            if (
                spell is not None
                and spell.execution_mode == SpellExecutionMode.SEQUENTIAL
            ):
                has_sequential = True
                break

        if has_sequential:
            return await self._dispatch_sequential(
                spell_casts, context, callbacks, emit, signal
            )
        return await self._dispatch_parallel(
            spell_casts, context, callbacks, emit, signal
        )

    async def _handle_truncated(
        self,
        spell_casts: list[dict[str, Any]],
        emit: EmitSink,
    ) -> BatchResult:
        messages: list[SpellResultMessage] = []
        for spell_cast in spell_casts:
            msg = _TRUNCATED_SPELL_CALL.format(name=spell_cast["name"])
            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_START,
                    data={
                        "spellCastId": spell_cast["id"],
                        "spellName": spell_cast["name"],
                        "arguments": spell_cast.get("arguments", {}),
                    },
                )
            )
            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_END,
                    data={"spellCastId": spell_cast["id"], "error": msg},
                )
            )
            messages.append(
                SpellResultMessage(
                    spell_cast_id=spell_cast["id"],
                    spell_name=spell_cast["name"],
                    content=[{"type": "text", "text": msg}],
                    is_error=True,
                )
            )
        return BatchResult(messages=messages, terminate=False)

    async def _dispatch_sequential(
        self,
        spell_casts: list[dict[str, Any]],
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> BatchResult:
        messages: list[SpellResultMessage] = []
        for spell_cast in spell_casts:
            if signal is not None and signal.aborted:
                raise AbortError("Operation aborted")
            res = await self._execute_single_spell(
                spell_cast, context, callbacks, emit, signal
            )
            if res is not None:
                messages.append(res)

        terminate = bool(messages) and all(m.terminate for m in messages)
        return BatchResult(messages=messages, terminate=terminate)

    async def _dispatch_parallel(
        self,
        spell_casts: list[dict[str, Any]],
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> BatchResult:
        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted")

        tasks = [
            self._execute_single_spell(spell_cast, context, callbacks, emit, signal)
            for spell_cast in spell_casts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        messages: list[SpellResultMessage] = []
        for res in results:
            if isinstance(res, SpellResultMessage):
                messages.append(res)
            elif isinstance(res, AbortError):
                raise res
        terminate = bool(messages) and all(m.terminate for m in messages)
        return BatchResult(messages=messages, terminate=terminate)

    async def _execute_single_spell(
        self,
        spell_cast: dict[str, Any],
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> SpellResultMessage | None:
        spell_name = spell_cast["name"]
        spell_cast_id = spell_cast["id"]

        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted")

        if callbacks.before_spell_cast is not None:
            blocked = await callbacks.before_spell_cast(
                {"spell_cast": spell_cast, "spell_name": spell_name}
            )
            if blocked:
                return None

        spell = context.get_spell(spell_name)
        if spell is None:
            err: MvgeError = SpellNotFoundError(spell_name)
            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_END,
                    data={
                        "spellCastId": spell_cast_id,
                        "error": err.code,
                        "message": str(err),
                    },
                )
            )
            return None

        await emit(
            MvgeEvent(
                type=MvgeEventType.SPELL_CASTING_START,
                data={
                    "spellCastId": spell_cast_id,
                    "spellName": spell_name,
                    "arguments": spell_cast.get("arguments", {}),
                },
            )
        )

        try:
            if signal is not None and signal.aborted:
                raise AbortError("Operation aborted")
            try:
                raw_result = await asyncio.wait_for(
                    spell.execute(
                        spell_cast_id,
                        spell_cast.get("arguments", {}),
                        signal=signal,
                    ),
                    timeout=context.spell_timeout_ms / 1000,
                )
            except asyncio.CancelledError as exc:
                if signal is not None and signal.aborted:
                    raise AbortError("Operation aborted") from exc
                raise

            is_error = False
            terminate = False
            result_content: Any = raw_result
            result_details: dict[str, Any] = {}

            if isinstance(raw_result, SpellResult):
                result_content = raw_result.content
                is_error = raw_result.status == "error"
                terminate = raw_result.terminate
                result_details = dict(raw_result.details)

            if callbacks.after_spell_result is not None:
                chained = await callbacks.after_spell_result(
                    {
                        "spell_name": spell_name,
                        "spell_cast_id": spell_cast_id,
                        "result": result_content,
                    }
                )
                if isinstance(chained, dict):
                    result_content = chained.get("result", result_content)

            result_text, result_details = _apply_backstop(
                str(result_content), result_details
            )
            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_END,
                    data={"spellCastId": spell_cast_id, "result": result_text},
                )
            )
            return SpellResultMessage(
                spell_cast_id=spell_cast_id,
                spell_name=spell_name,
                content=[{"type": "text", "text": result_text}],
                details=result_details or None,
                is_error=is_error,
                terminate=terminate,
            )
        except TimeoutError:
            err = SpellTimeoutError(spell_name, context.spell_timeout_ms)
        except AbortError:
            raise
        except Exception as exc:
            err = to_error(exc)

        await emit(
            MvgeEvent(
                type=MvgeEventType.SPELL_CASTING_END,
                data={"spellCastId": spell_cast_id, "error": str(err)},
            )
        )
        return SpellResultMessage(
            spell_cast_id=spell_cast_id,
            spell_name=spell_name,
            content=[{"type": "text", "text": str(err)}],
            is_error=True,
            terminate=False,
        )
