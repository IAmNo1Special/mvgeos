from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mvgeos_agent.core_loop import LoopCallbacks, LoopContext
from mvgeos_agent.dispatcher import BatchResult, SpellDispatcher
from mvgeos_agent.types import (
    MvgeEvent,
    MvgeResponse,
    MvgeSpell,
    SpellExecutionMode,
    SpellResult,
    StopReason,
)


class SlowMockSpell(MvgeSpell):
    def __init__(self, name: str, delay_s: float, result_text: str) -> None:
        super().__init__(
            name=name,
            description=f"Mock spell {name}",
            parameters={},
            execution_mode=SpellExecutionMode.PARALLEL,
        )
        self.delay_s = delay_s
        self.result_text = result_text

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> str:
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        return self.result_text


class FailingSpell(MvgeSpell):
    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            description=f"Failing spell {name}",
            parameters={},
            execution_mode=SpellExecutionMode.PARALLEL,
        )

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> str:
        raise ValueError("Spell internal failure")


class TerminatingSpell(MvgeSpell):
    def __init__(self, name: str, terminate: bool) -> None:
        super().__init__(
            name=name,
            description=f"Terminating spell {name}",
            parameters={},
            execution_mode=SpellExecutionMode.PARALLEL,
        )
        self.terminate = terminate

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> SpellResult:
        return SpellResult(
            spell_name=self.name,
            content=f"Result of {self.name}",
            terminate=self.terminate,
        )


class SequentialSpell(MvgeSpell):
    def __init__(self, name: str, result_text: str) -> None:
        super().__init__(
            name=name,
            description=f"Sequential spell {name}",
            parameters={},
            execution_mode=SpellExecutionMode.SEQUENTIAL,
        )
        self.result_text = result_text

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> str:
        return self.result_text


@pytest.mark.asyncio
async def test_dispatch_parallel_execution() -> None:
    events: list[MvgeEvent] = []

    async def emit(event: MvgeEvent) -> None:
        events.append(event)

    spell_a = SlowMockSpell("spell_a", delay_s=0.05, result_text="output_a")
    spell_b = SlowMockSpell("spell_b", delay_s=0.05, result_text="output_b")

    dispatcher = SpellDispatcher()
    context = LoopContext(spells=[spell_a, spell_b])
    callbacks = LoopCallbacks()

    inv = MvgeResponse(
        stop_reason=StopReason.SPELL_USE,
        content=[
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "spell_a", "arguments": {}},
            },
            {
                "type": "tool_call",
                "tool_call": {"id": "call_2", "name": "spell_b", "arguments": {}},
            },
        ],
    )

    start_time = asyncio.get_running_loop().time()
    res: BatchResult = await dispatcher.dispatch_batch(
        inv=inv,
        context=context,
        callbacks=callbacks,
        emit=emit,
    )
    elapsed = asyncio.get_running_loop().time() - start_time

    # Both delay 0.05s, parallel execution finishes well under sequential time (~0.10s)
    assert elapsed < 0.2
    assert len(res.messages) == 2
    assert res.messages[0].spell_name == "spell_a"
    assert res.messages[1].spell_name == "spell_b"
    assert "output_a" in str(res.messages[0].content)
    assert "output_b" in str(res.messages[1].content)
    assert res.terminate is False


@pytest.mark.asyncio
async def test_dispatch_preserves_request_order() -> None:
    events: list[MvgeEvent] = []

    async def emit(event: MvgeEvent) -> None:
        events.append(event)

    # spell_a takes longer than spell_b
    spell_a = SlowMockSpell("spell_a", delay_s=0.06, result_text="output_a")
    spell_b = SlowMockSpell("spell_b", delay_s=0.01, result_text="output_b")

    dispatcher = SpellDispatcher()
    context = LoopContext(spells=[spell_a, spell_b])

    inv = MvgeResponse(
        stop_reason=StopReason.SPELL_USE,
        content=[
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "spell_a", "arguments": {}},
            },
            {
                "type": "tool_call",
                "tool_call": {"id": "call_2", "name": "spell_b", "arguments": {}},
            },
        ],
    )

    res = await dispatcher.dispatch_batch(
        inv=inv,
        context=context,
        callbacks=LoopCallbacks(),
        emit=emit,
    )

    # Results must preserve request order [call_1, call_2]
    # even if spell_b finishes first
    assert res.messages[0].spell_cast_id == "call_1"
    assert res.messages[0].spell_name == "spell_a"
    assert res.messages[1].spell_cast_id == "call_2"
    assert res.messages[1].spell_name == "spell_b"


@pytest.mark.asyncio
async def test_dispatch_sequential_fallback() -> None:
    events: list[MvgeEvent] = []

    async def emit(event: MvgeEvent) -> None:
        events.append(event)

    spell_parallel = SlowMockSpell("spell_p", delay_s=0.03, result_text="output_p")
    spell_sequential = SequentialSpell("spell_s", result_text="output_s")

    dispatcher = SpellDispatcher()
    context = LoopContext(spells=[spell_parallel, spell_sequential])

    inv = MvgeResponse(
        stop_reason=StopReason.SPELL_USE,
        content=[
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "spell_p", "arguments": {}},
            },
            {
                "type": "tool_call",
                "tool_call": {"id": "call_2", "name": "spell_s", "arguments": {}},
            },
        ],
    )

    res = await dispatcher.dispatch_batch(
        inv=inv,
        context=context,
        callbacks=LoopCallbacks(),
        emit=emit,
    )

    assert len(res.messages) == 2
    assert res.messages[0].spell_name == "spell_p"
    assert res.messages[1].spell_name == "spell_s"


@pytest.mark.asyncio
async def test_dispatch_handles_isolated_failure() -> None:
    events: list[MvgeEvent] = []

    async def emit(event: MvgeEvent) -> None:
        events.append(event)

    spell_good = SlowMockSpell("spell_good", delay_s=0.01, result_text="good")
    spell_bad = FailingSpell("spell_bad")

    dispatcher = SpellDispatcher()
    context = LoopContext(spells=[spell_good, spell_bad])

    inv = MvgeResponse(
        stop_reason=StopReason.SPELL_USE,
        content=[
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "spell_good", "arguments": {}},
            },
            {
                "type": "tool_call",
                "tool_call": {"id": "call_2", "name": "spell_bad", "arguments": {}},
            },
        ],
    )

    res = await dispatcher.dispatch_batch(
        inv=inv,
        context=context,
        callbacks=LoopCallbacks(),
        emit=emit,
    )

    assert len(res.messages) == 2
    assert res.messages[0].is_error is False
    assert "good" in str(res.messages[0].content)
    assert res.messages[1].is_error is True
    assert "Spell internal failure" in str(res.messages[1].content)


@pytest.mark.asyncio
async def test_dispatch_truncated_length_stop() -> None:
    events: list[MvgeEvent] = []

    async def emit(event: MvgeEvent) -> None:
        events.append(event)

    spell = SlowMockSpell("spell_a", delay_s=0.01, result_text="good")
    dispatcher = SpellDispatcher()
    context = LoopContext(spells=[spell])

    inv = MvgeResponse(
        stop_reason=StopReason.LENGTH,
        content=[
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "spell_a", "arguments": {}},
            }
        ],
    )

    res = await dispatcher.dispatch_batch(
        inv=inv,
        context=context,
        callbacks=LoopCallbacks(),
        emit=emit,
    )

    assert len(res.messages) == 1
    assert res.messages[0].is_error is True
    assert "Mana limit" in str(res.messages[0].content) or "truncated" in str(
        res.messages[0].content
    )


@pytest.mark.asyncio
async def test_dispatch_batch_termination() -> None:
    events: list[MvgeEvent] = []

    async def emit(event: MvgeEvent) -> None:
        events.append(event)

    spell_t1 = TerminatingSpell("spell_t1", terminate=True)
    spell_t2 = TerminatingSpell("spell_t2", terminate=True)

    dispatcher = SpellDispatcher()
    context = LoopContext(spells=[spell_t1, spell_t2])

    inv = MvgeResponse(
        stop_reason=StopReason.SPELL_USE,
        content=[
            {
                "type": "tool_call",
                "tool_call": {"id": "call_1", "name": "spell_t1", "arguments": {}},
            },
            {
                "type": "tool_call",
                "tool_call": {"id": "call_2", "name": "spell_t2", "arguments": {}},
            },
        ],
    )

    res = await dispatcher.dispatch_batch(
        inv=inv,
        context=context,
        callbacks=LoopCallbacks(),
        emit=emit,
    )

    assert len(res.messages) == 2
    assert res.terminate is True
