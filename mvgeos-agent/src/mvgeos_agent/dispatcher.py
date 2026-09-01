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


@dataclass
class BatchResult:
    """The outcome of a batch of spell cast requests."""

    messages: list[SpellResultMessage] = field(default_factory=list)
    terminate: bool = False


class SpellDispatcher:
    """Deep module for executing tool call batches concurrently or sequentially.

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
        tool_calls = [
            item["tool_call"]
            for item in inv.content or []
            if item.get("type") == ContentType.TOOL_CALL
        ]
        if not tool_calls:
            return BatchResult()

        if inv.stop_reason == StopReason.LENGTH:
            return await self._handle_truncated(tool_calls, emit)

        # If any spell in batch requests sequential, run sequentially
        has_sequential = False
        for tool_call in tool_calls:
            spell_name = tool_call.get("name")
            spell = context.get_spell(spell_name) if spell_name else None
            if (
                spell is not None
                and spell.execution_mode == SpellExecutionMode.SEQUENTIAL
            ):
                has_sequential = True
                break

        if has_sequential:
            return await self._dispatch_sequential(
                tool_calls, context, callbacks, emit, signal
            )
        return await self._dispatch_parallel(
            tool_calls, context, callbacks, emit, signal
        )

    async def _handle_truncated(
        self,
        tool_calls: list[dict[str, Any]],
        emit: EmitSink,
    ) -> BatchResult:
        messages: list[SpellResultMessage] = []
        for tool_call in tool_calls:
            msg = _TRUNCATED_SPELL_CALL.format(name=tool_call["name"])
            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_START,
                    data={
                        "spellCastId": tool_call["id"],
                        "spellName": tool_call["name"],
                        "arguments": tool_call.get("arguments", {}),
                    },
                )
            )
            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_END,
                    data={"spellCastId": tool_call["id"], "error": msg},
                )
            )
            messages.append(
                SpellResultMessage(
                    spell_cast_id=tool_call["id"],
                    spell_name=tool_call["name"],
                    content=[{"type": "text", "text": msg}],
                    is_error=True,
                )
            )
        return BatchResult(messages=messages, terminate=False)

    async def _dispatch_sequential(
        self,
        tool_calls: list[dict[str, Any]],
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> BatchResult:
        messages: list[SpellResultMessage] = []
        for tool_call in tool_calls:
            if signal is not None and signal.aborted:
                raise AbortError("Operation aborted")
            res = await self._execute_single_spell(
                tool_call, context, callbacks, emit, signal
            )
            if res is not None:
                messages.append(res)

        terminate = bool(messages) and all(m.terminate for m in messages)
        return BatchResult(messages=messages, terminate=terminate)

    async def _dispatch_parallel(
        self,
        tool_calls: list[dict[str, Any]],
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> BatchResult:
        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted")

        tasks = [
            self._execute_single_spell(tool_call, context, callbacks, emit, signal)
            for tool_call in tool_calls
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
        tool_call: dict[str, Any],
        context: LoopContext,
        callbacks: LoopCallbacks,
        emit: EmitSink,
        signal: AbortSignal | None = None,
    ) -> SpellResultMessage | None:
        spell_name = tool_call["name"]
        spell_cast_id = tool_call["id"]

        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted")

        if callbacks.before_spell_cast is not None:
            blocked = await callbacks.before_spell_cast(
                {"tool_call": tool_call, "spell_name": spell_name}
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
                    "arguments": tool_call.get("arguments", {}),
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
                        tool_call.get("arguments", {}),
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

            if isinstance(raw_result, SpellResult):
                result_content = raw_result.content
                is_error = raw_result.status == "error"
                terminate = raw_result.terminate

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

            await emit(
                MvgeEvent(
                    type=MvgeEventType.SPELL_CASTING_END,
                    data={"spellCastId": spell_cast_id, "result": result_content},
                )
            )
            return SpellResultMessage(
                spell_cast_id=spell_cast_id,
                spell_name=spell_name,
                content=[{"type": "text", "text": str(result_content)}],
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
