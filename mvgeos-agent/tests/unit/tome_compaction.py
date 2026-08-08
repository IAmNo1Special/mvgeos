from __future__ import annotations

import tempfile
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntryType

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.types import StopReason, SummonerRequest


def _tome(tmp: str) -> tuple[MvgeTome, TomeLedger]:
    ledger = TomeLedger(Path(tmp))
    meta = ledger.create_tome("/tmp")
    return MvgeTome(ledger, meta), ledger


class TestRecordCompaction:
    def test_appends_compaction_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)
            tome._started = True

            tome.record_compaction(
                summary="## Goal\nShip it.",
                mana_before=5000,
                retained_tail=[SummonerRequest(role="user", content="keep me")],
            )

            entries = ledger.get_entries(tome.tome_id, TomeEntryType.COMPACTION)
            assert len(entries) == 1

    def test_payload_carries_pi_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)
            tome._started = True

            tome.record_compaction(
                summary="## Goal\nShip it.",
                mana_before=5000,
                retained_tail=[SummonerRequest(role="user", content="keep me")],
            )

            entry = ledger.get_entries(tome.tome_id, TomeEntryType.COMPACTION)[0]
            assert entry.payload["summary"] == "## Goal\nShip it."
            assert entry.payload["manaBefore"] == 5000
            assert entry.payload["retainedTail"]

    def test_retained_tail_is_serialisable(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)
            tome._started = True

            tome.record_compaction(
                summary="s",
                mana_before=1,
                retained_tail=[SummonerRequest(role="user", content="keep me")],
            )

            entry = ledger.get_entries(tome.tome_id, TomeEntryType.COMPACTION)[0]
            # Round-trips through JSON exactly as the Tome file requires.
            assert json.loads(json.dumps(entry.payload))

    def test_dropped_when_tome_not_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)

            result = tome.record_compaction(
                summary="s", mana_before=1, retained_tail=[]
            )

            assert result is None
            assert ledger.get_entries(tome.tome_id, TomeEntryType.COMPACTION) == []

    def test_records_first_kept_entry_id_when_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)
            tome._started = True

            tome.record_compaction(
                summary="s",
                mana_before=1,
                retained_tail=[],
                first_kept_entry_id="abc123",
            )

            entry = ledger.get_entries(tome.tome_id, TomeEntryType.COMPACTION)[0]
            assert entry.payload["firstKeptEntryId"] == "abc123"

    def test_serialises_mvge_response_tail(self) -> None:
        from mvgeos_agent.types import MvgeResponse

        with tempfile.TemporaryDirectory() as tmp:
            tome, ledger = _tome(tmp)
            tome._started = True

            tome.record_compaction(
                summary="s",
                mana_before=1,
                retained_tail=[
                    MvgeResponse(
                        role="assistant",
                        content=[{"type": "text", "text": "hi"}],
                        stop_reason=StopReason.STOP,
                    )
                ],
            )

            entry = ledger.get_entries(tome.tome_id, TomeEntryType.COMPACTION)[0]
            tail = entry.payload["retainedTail"]
            assert tail[0]["role"] == "assistant"
