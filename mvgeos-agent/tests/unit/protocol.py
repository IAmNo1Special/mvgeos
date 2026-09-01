from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from coding_mvge import CodingMvge

from mvgeos_agent import BaseMvge, MvgeAgent
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeInvocation,
    MvgeResponse,
    QueueMode,
)


class DummyAgent:
    """Mock agent implementing the MvgeAgent protocol without inheriting BaseMvge."""

    def __init__(self) -> None:
        self.queue_mode: QueueMode = QueueMode.ONE_AT_A_TIME
        self.environment = MvgeEnvironment.resolve(
            agent_name="dummy", allow_unknown_agent=True
        )

    @property
    def tome_id(self) -> str | None:
        return "tome-123"

    @property
    def session_id(self) -> str | None:
        return self.tome_id

    @property
    def model_id(self) -> str:
        return "test/model"

    @property
    def contemplation_level(self) -> ContemplationLevel | str:
        return "medium"

    @property
    def mana_used(self) -> int | None:
        return 42

    @property
    def enabled_spells(self) -> list[str]:
        return ["read", "write"]

    @property
    def registered_providers(self) -> list[str]:
        return ["openrouter"]

    def on(
        self,
        event_type: Any,
        callback: Any,
    ) -> Any:
        return lambda: None

    def steer(self, text: str) -> None:
        pass

    def follow_up(self, text: str) -> None:
        pass

    def queue(self, text: str) -> None:
        pass

    def abort(self) -> None:
        pass

    async def initialize(self) -> None:
        pass

    async def run(self, prompt: str) -> MvgeInvocation:
        return MvgeResponse(content=[{"type": "text", "text": "ok"}])

    async def switch_model(self, model_id: str) -> None:
        pass

    def build_snapshot(self) -> Any:
        return None

    async def close(self) -> None:
        pass


class TestMvgeAgentProtocol:
    def test_base_mvge_conforms(self) -> None:
        agent = BaseMvge(api_key="test-key")
        assert isinstance(agent, MvgeAgent)
        assert agent.session_id == agent.tome_id
        assert agent.model_id == agent._model_id
        assert agent.contemplation_level == agent._contemplation_level
        assert agent.mana_used is None
        assert isinstance(agent.enabled_spells, list)

    def test_coding_mvge_conforms(self) -> None:
        agent = CodingMvge(api_key="test-key")
        assert isinstance(agent, MvgeAgent)
        assert agent.session_id == agent.tome_id
        assert agent.model_id == agent._model_id
        assert "bash" in agent.enabled_spells

    def test_dummy_agent_conforms(self) -> None:
        dummy = DummyAgent()
        assert isinstance(dummy, MvgeAgent)
        assert dummy.session_id == "tome-123"
        assert dummy.mana_used == 42
        assert dummy.model_id == "test/model"

    def test_incomplete_agent_fails_conformance(self) -> None:
        class IncompleteAgent:
            pass

        assert not isinstance(IncompleteAgent(), MvgeAgent)

    @pytest.mark.asyncio
    async def test_base_mvge_mana_used_with_state(self) -> None:
        agent = BaseMvge(api_key="test-key")
        state_mock = MagicMock()
        state_mock.mana_used = 1337
        agent._state = state_mock  # type: ignore[attr-defined]
        assert agent.mana_used == 1337

    @pytest.mark.asyncio
    async def test_base_mvge_load_runes_method(self) -> None:
        agent = BaseMvge(api_key="test-key")
        agent._load_runes = AsyncMock()  # type: ignore[method-assign]
        await agent.load_runes()
        agent._load_runes.assert_awaited_once()
