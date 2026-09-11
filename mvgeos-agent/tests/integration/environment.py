from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_core.channel import Model
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook

from mvgeos_agent.mvge import Mvge


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


def _agent(tome_dir: Path) -> Mvge:
    agent = Mvge(api_key="test-key", tome_dir=tome_dir)
    agent._provider_registry.resolve = MagicMock(  # type: ignore[method-assign]
        return_value=(_mock_model(), MagicMock())
    )
    return agent


@pytest.mark.asyncio
async def test_system_prompt_matches_environment_assemble() -> None:
    """BaseMvge's async prompt path and MvgeEnvironment.assemble_system_prompt
    must produce identical prompts for the same inputs."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = _agent(Path(tmp))
        await agent.initialize()

        assert agent._state is not None
        expected = await agent._environment.assemble_system_prompt(
            runner=agent._runner,
            base_prompt=agent._build_system_prompt(),
            custom_prompt=getattr(agent, "_custom_system_prompt", ""),
            cwd=Path.cwd(),
            spell_names=[s.name for s in agent._build_spells()],
            config_dir=agent.config_dir,
        )

        assert agent._state.system_prompt == expected
        assert await agent._build_system_prompt_async() == expected


@pytest.mark.asyncio
async def test_render_prompt_matches_environment_render() -> None:
    from mvgeos_agent.environment import MvgeEnvironment as Env
    from mvgeos_agent.environment import render_prompt as free_render

    with tempfile.TemporaryDirectory() as tmp:
        agent = _agent(Path(tmp))
        cwd = str(getattr(agent._config_manager, "_project_dir", "") or Path.cwd())
        expected = free_render(
            "You are Mvge",
            ["bash"],
            ["Be concise."],
            cwd=cwd,
            runes_paths=agent._environment.runes_paths,
            system_path=agent._environment.resolved_prompt.path,
            guidelines_path=agent._environment.resolved_guidelines.path,
        )

        assert (
            Env.render_prompt(
                "You are Mvge",
                ["bash"],
                ["Be concise."],
                cwd=cwd,
                runes_paths=agent._environment.runes_paths,
                system_path=agent._environment.resolved_prompt.path,
                guidelines_path=agent._environment.resolved_guidelines.path,
            )
            == expected
        )


@pytest.mark.asyncio
async def test_initialize_fires_before_mvge_start_once() -> None:
    """BEFORE_MVGE_START flows through MvgeEnvironment exactly once per init."""
    with tempfile.TemporaryDirectory() as tmp:
        agent = _agent(Path(tmp))
        agent._load_runes = AsyncMock()  # type: ignore[method-assign]
        agent._runner = RuneRunner()

        calls: list[Any] = []

        def recorder(data: Any) -> None:
            calls.append(data)

        agent._runner.register_handler(SigilHook.BEFORE_MVGE_START, recorder)

        await agent.initialize()

        assert len(calls) == 1
        assert calls[0].agent_name == "default-mvge"
