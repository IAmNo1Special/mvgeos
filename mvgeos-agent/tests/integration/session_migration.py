from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mvgeos_provider.base import Realm
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_tome import CURRENT_SESSION_VERSION, TomeLedger
from mvgeos_tome.types import TomeEntryType

from mvgeos_agent.mvge import Mvge
from mvgeos_agent.types import (
    ContentType,
    MvgeInvocation,
    MvgeResponse,
    StopReason,
    SummonerRequest,
)


def _write_fixture_session(
    tome_dir: Path, filename: str, lines: list[dict[str, Any]]
) -> Path:
    target = tome_dir / filename
    with target.open("w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")
    return target


def _create_mock_realm(response_text: str = "mock agent answer") -> Realm:
    realm = MagicMock(spec=Realm)

    async def mock_stream(
        model: Model,
        invocations: list[MvgeInvocation],
        config: ChannelConfig | None = None,
        signal: Any | None = None,
    ) -> AsyncIterator[RealmResponse]:
        yield RealmResponse(
            model=model,
            invocation=MvgeResponse(
                role="assistant",
                content=[{"type": ContentType.TEXT, "text": response_text}],
                stop_reason=StopReason.STOP,
            ),
        )

    realm.stream = mock_stream  # type: ignore[method-assign]
    return realm


def _mock_model() -> Model:
    return Model(
        id="test-model",
        name="test-model",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        context_window=4096,
        max_tokens=1024,
    )


@pytest.mark.asyncio
async def test_resume_legacy_v1_session_seamless_migration_and_execution() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome_dir = Path(tmp)
        # Create legacy v1 session file (no version field, flat entries)
        header = {
            "type": "session",
            "id": "legacy-v1-tome",
            "timestamp": "2026-06-01T10:00:00Z",
            "cwd": "/workspace/test",
        }
        e1 = {
            "type": "message",
            "timestamp": 1000.0,
            "payload": {"role": "user", "content": "What is 2+2?"},
        }
        e2 = {
            "type": "message",
            "timestamp": 1001.0,
            "payload": {
                "role": "assistant",
                "content": [{"type": "text", "text": "2+2 is 4"}],
            },
        }
        _write_fixture_session(tome_dir, "legacy-v1-tome.jsonl", [header, e1, e2])

        # Resume agent with legacy-v1-tome
        agent = Mvge(
            api_key="test-key",
            tome_dir=tome_dir,
            tome_resume="legacy-v1-tome",
        )
        mock_realm = _create_mock_realm("It is an arithmetic operation.")
        agent._provider_registry.resolve = MagicMock(  # type: ignore[method-assign]
            return_value=(_mock_model(), mock_realm)
        )

        await agent.initialize()

        assert agent._agent_tome is not None
        assert agent._agent_tome.tome_id == "legacy-v1-tome"
        assert agent._agent_tome.version == CURRENT_SESSION_VERSION
        assert agent._agent_tome.metadata.version == CURRENT_SESSION_VERSION

        # Verify historical invocations were reconstructed
        assert agent._state is not None
        assert len(agent._state.invocations) == 2
        assert isinstance(agent._state.invocations[0], SummonerRequest)
        assert agent._state.invocations[0].content == "What is 2+2?"
        assert isinstance(agent._state.invocations[1], MvgeResponse)

        # Run a new turn
        response = await agent.run("Why is that?")
        assert isinstance(response, MvgeResponse)
        assert response.content == [
            {"type": ContentType.TEXT, "text": "It is an arithmetic operation."}
        ]

        # Verify new messages were appended to the tome ledger
        ledger = TomeLedger(tome_dir)
        entries = ledger.get_entries("legacy-v1-tome")
        message_entries = [e for e in entries if e.type == TomeEntryType.MESSAGE]
        assert len(message_entries) == 4
        assert message_entries[0].payload["content"] == "What is 2+2?"
        assert message_entries[2].payload["content"] == "Why is that?"
        assert message_entries[2].parent_id == message_entries[1].id
        assert message_entries[3].parent_id == message_entries[2].id

        await agent.close()


@pytest.mark.asyncio
async def test_resume_legacy_v2_session_with_hook_messages_and_compaction() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome_dir = Path(tmp)
        # Create a legacy v2 session fixture with legacy hookMessage and spellResult
        header = {
            "type": "session",
            "version": 2,
            "id": "legacy-v2-tome",
            "timestamp": "2026-06-01T10:00:00Z",
            "cwd": "/workspace/test",
            "activeLeafId": "msg-2",
        }
        e1 = {
            "id": "msg-1",
            "parentId": None,
            "type": "message",
            "timestamp": 1000.0,
            "payload": {"role": "user", "content": "Execute spell"},
        }
        e2 = {
            "id": "msg-2",
            "parentId": "msg-1",
            "type": "spellResult",
            "timestamp": 1001.0,
            "payload": {
                "role": "tool",
                "spell_name": "bash",
                "spell_cast_id": "call-1",
                "content": [{"type": "text", "text": "result ok"}],
            },
        }
        e3 = {
            "id": "msg-3",
            "parentId": "msg-2",
            "type": "hookMessage",
            "timestamp": 1002.0,
            "payload": {"role": "hookMessage", "content": "sigil event"},
        }
        _write_fixture_session(tome_dir, "legacy-v2-tome.jsonl", [header, e1, e2, e3])

        agent = Mvge(
            api_key="test-key",
            tome_dir=tome_dir,
            tome_resume="legacy-v2-tome",
        )
        mock_realm = _create_mock_realm("Done")
        agent._provider_registry.resolve = MagicMock(  # type: ignore[method-assign]
            return_value=(_mock_model(), mock_realm)
        )

        await agent.initialize()

        assert agent._agent_tome is not None
        assert agent._agent_tome.version == 3

        # Check entries migrated in ledger
        ledger = TomeLedger(tome_dir)
        entries = ledger.get_entries("legacy-v2-tome")
        assert len(entries) == 3
        assert entries[0].type == TomeEntryType.MESSAGE
        assert entries[1].type == TomeEntryType.MESSAGE
        assert entries[2].type == TomeEntryType.CUSTOM

        # Run follow-up turn
        response = await agent.run("Next step")
        assert isinstance(response, MvgeResponse)

        await agent.close()


@pytest.mark.asyncio
async def test_reopen_migrated_session_in_fresh_agent_instance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tome_dir = Path(tmp)
        header = {
            "type": "session",
            "id": "roundtrip-agent-tome",
            "timestamp": "2026-06-01T10:00:00Z",
            "cwd": "/workspace/test",
        }
        e1 = {
            "type": "message",
            "timestamp": 1000.0,
            "payload": {"role": "user", "content": "First turn"},
        }
        _write_fixture_session(tome_dir, "roundtrip-agent-tome.jsonl", [header, e1])

        # 1. First agent resumes v1 session and executes a turn
        agent1 = Mvge(
            api_key="test-key",
            tome_dir=tome_dir,
            tome_resume="roundtrip-agent-tome",
        )
        agent1._provider_registry.resolve = MagicMock(  # type: ignore[method-assign]
            return_value=(_mock_model(), _create_mock_realm("Response 1"))
        )
        await agent1.initialize()
        await agent1.run("User message 2")
        await agent1.close()

        # 2. Second agent opens the same session
        agent2 = Mvge(
            api_key="test-key",
            tome_dir=tome_dir,
            tome_resume="roundtrip-agent-tome",
        )
        agent2._provider_registry.resolve = MagicMock(  # type: ignore[method-assign]
            return_value=(_mock_model(), _create_mock_realm("Response 2"))
        )
        await agent2.initialize()

        assert agent2._agent_tome is not None
        assert agent2._state is not None
        # Should have: First turn (user), User message 2 (user), Response 1 (assistant)
        assert len(agent2._state.invocations) == 3

        resp2 = await agent2.run("User message 3")
        assert isinstance(resp2, MvgeResponse)
        assert resp2.content == [{"type": ContentType.TEXT, "text": "Response 2"}]

        await agent2.close()
