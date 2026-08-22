from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_provider.types import Model
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.prompt_assembly import PromptAssembly


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


def _agent(tome_dir: Path) -> BaseMvge:
    agent = BaseMvge(api_key="test-key", tome_dir=tome_dir)
    agent._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
    agent._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
    return agent


@pytest.mark.asyncio
async def test_system_prompt_matches_prompt_assembly() -> None:
    """Issue #93: BaseMvge's async prompt path and PromptAssembly must produce
    identical prompts for the same inputs."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = _agent(Path(tmp))
        await agent.initialize()

        assert agent._state is not None
        expected = await PromptAssembly(
            base_prompt=agent._build_system_prompt(),
            agent_name=agent._name,
            config_dir=agent.config_dir,
            custom_prompt=getattr(agent, "_custom_system_prompt", ""),
            cwd=Path.cwd(),
            runner=agent._runner,
        ).assemble()

        assert agent._state.system_prompt == expected
        assert await agent._build_system_prompt_async() == expected


@pytest.mark.asyncio
async def test_render_prompt_matches_prompt_assembly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        agent = _agent(Path(tmp))

        cwd = str(getattr(agent._config_manager, "_project_dir", "") or Path.cwd())
        expected = PromptAssembly(cwd=cwd, runner=agent._runner).render(
            "You are Mvge", ["bash"], ["Be concise."]
        )

        assert agent._render_prompt("You are Mvge", ["bash"], ["Be concise."]) == (
            expected
        )


@pytest.mark.asyncio
async def test_initialize_fires_before_mvge_start_once() -> None:
    """BEFORE_MVGE_START flows through PromptAssembly exactly once per init."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = _agent(Path(tmp))
        agent._load_runes = AsyncMock()  # type: ignore[method-assign]
        agent._runner = RuneRunner()

        calls: list[Any] = []

        def recorder(data: dict) -> None:
            calls.append(dict(data.items()))

        agent._runner.register_handler(SigilHook.BEFORE_MVGE_START, recorder)

        await agent.initialize()

        assert len(calls) == 1
        assert calls[0]["agent_name"] == "default-mvge"
