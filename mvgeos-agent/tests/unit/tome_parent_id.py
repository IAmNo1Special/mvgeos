from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.mvge_loop import MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    ContentType,
    MvgeEvent,
    MvgeEventType,
    MvgeResponse,
    MvgeState,
    SpellResultMessage,
    StopReason,
    SummonerRequest,
)


def _tome(tmp: str) -> tuple[MvgeTome, TomeLedger]:
    ledger = TomeLedger(Path(tmp))
    meta = ledger.create_tome("/tmp")
    tome = MvgeTome(ledger, meta)
    tome._started = True
    return tome, ledger


class TestMvgeTomeParentId:
    def test_record_message_defaults_parent_id_to_active_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)

            assert tome.active_leaf_id is None

            # First message has parent_id = None
            e1 = tome.record_message(role="user", content="msg 1")
            assert e1 is not None
            assert e1.parent_id is None
            assert tome.active_leaf_id == e1.id

            # Second message automatically receives e1.id as parent_id
            e2 = tome.record_message(role="assistant", content="msg 2")
            assert e2 is not None
            assert e2.parent_id == e1.id
            assert tome.active_leaf_id == e2.id

            # Third message automatically receives e2.id as parent_id
            e3 = tome.record_message(role="user", content="msg 3")
            assert e3 is not None
            assert e3.parent_id == e2.id
            assert tome.active_leaf_id == e3.id


class TestMvgeLoopRecordInvocationParentId:
    @pytest.mark.asyncio
    async def test_record_invocation_supplies_active_leaf_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)

            state = MvgeState(
                system_prompt="test",
                prompt_source="system",
                model={"id": "openrouter/meta-llama/llama-3"},
                contemplation_level=ContemplationLevel.OFF,
                spells=[],
                invocations=[],
                agent_tome=tome,
            )
            loop = MvgeLoop(state)

            # Record SummonerRequest
            req = SummonerRequest(role="user", content="hello")
            event1 = MvgeEvent(
                type=MvgeEventType.MESSAGE_END,
                data={"invocation": req},
            )
            await loop._record_invocation(event1)

            e1_id = tome.active_leaf_id
            assert e1_id is not None
            entry1 = ledger.get_entry(tome.tome_id, e1_id)
            assert entry1 is not None
            assert entry1.parent_id is None

            # Record MvgeResponse
            resp = MvgeResponse(
                role="assistant",
                content=[{"type": ContentType.TEXT, "text": "calling tool"}],
                stop_reason=StopReason.SPELL_USE,
            )
            event2 = MvgeEvent(
                type=MvgeEventType.MESSAGE_END,
                data={"invocation": resp},
            )
            await loop._record_invocation(event2)

            e2_id = tome.active_leaf_id
            assert e2_id is not None
            assert e2_id != e1_id
            entry2 = ledger.get_entry(tome.tome_id, e2_id)
            assert entry2 is not None
            assert entry2.parent_id == e1_id

            # Record SpellResultMessage
            result = SpellResultMessage(
                role="spellResult",
                spell_name="bash",
                spell_cast_id="call_1",
                content=[{"type": ContentType.TEXT, "text": "tool output"}],
            )
            event3 = MvgeEvent(
                type=MvgeEventType.MESSAGE_END,
                data={"invocation": result},
            )
            await loop._record_invocation(event3)

            e3_id = tome.active_leaf_id
            assert e3_id is not None
            assert e3_id != e2_id
            entry3 = ledger.get_entry(tome.tome_id, e3_id)
            assert entry3 is not None
            assert entry3.parent_id == e2_id

            # Context lookup from e3_id should reconstruct [entry1, entry2, entry3]
            context = ledger.get_entries_for_context(tome.tome_id, leaf_id=e3_id)
            assert [e.id for e in context] == [e1_id, e2_id, e3_id]
