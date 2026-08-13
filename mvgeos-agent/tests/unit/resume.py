from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_provider.types import Model

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.types import SessionResumeError


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
async def test_resume_session_resolves_prefix_id() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_dir = Path(tmp_dir)

        # Create agent to create initial tome
        agent1 = BaseMvge(api_key="test-key", session_dir=session_dir)
        agent1._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent1._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent1,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent1.initialize()

        assert agent1._agent_session is not None
        actual_id = agent1._agent_session.tome_id

        # Now resume using prefix ID
        prefix = actual_id[:8]
        agent2 = BaseMvge(
            api_key="test-key", session_dir=session_dir, session_resume=prefix
        )
        agent2._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent2._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent2,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent2.initialize()

        assert agent2._agent_session is not None
        assert agent2._agent_session.tome_id == actual_id


@pytest.mark.asyncio
async def test_resume_session_resolves_full_id() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_dir = Path(tmp_dir)

        agent1 = BaseMvge(api_key="test-key", session_dir=session_dir)
        agent1._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent1._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent1,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent1.initialize()

        assert agent1._agent_session is not None
        actual_id = agent1._agent_session.tome_id

        agent2 = BaseMvge(
            api_key="test-key", session_dir=session_dir, session_resume=actual_id
        )
        agent2._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent2._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent2,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent2.initialize()

        assert agent2._agent_session is not None
        assert agent2._agent_session.tome_id == actual_id


@pytest.mark.asyncio
async def test_resume_session_resolves_raw_path() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_dir = Path(tmp_dir)

        agent1 = BaseMvge(api_key="test-key", session_dir=session_dir)
        agent1._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent1._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent1,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent1.initialize()

        assert agent1._agent_session is not None
        actual_id = agent1._agent_session.tome_id
        raw_path = session_dir / f"{actual_id}.jsonl"

        agent2 = BaseMvge(
            api_key="test-key", session_dir=session_dir, session_resume=str(raw_path)
        )
        agent2._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent2._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent2,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent2.initialize()

        assert agent2._agent_session is not None
        assert agent2._agent_session.tome_id == actual_id


@pytest.mark.asyncio
async def test_resume_session_missing_id_raises_error() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_dir = Path(tmp_dir)

        agent = BaseMvge(
            api_key="test-key", session_dir=session_dir, session_resume="nonexistent_id"
        )
        agent._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with (
            patch.object(
                agent,
                "_build_system_prompt_async",
                new_callable=AsyncMock,
                return_value="sys",
            ),
            pytest.raises(SessionResumeError) as exc_info,
        ):
            await agent.initialize()

        assert "nonexistent_id" in str(exc_info.value)
