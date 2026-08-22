from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import BeforeMvgeStartData, SigilHook

from mvgeos_agent.prompt_assembly import PromptAssembly
from mvgeos_agent.prompt_config import _render_prompt


def _mock_runner(*, suppressed: bool = False, catalog: str = "") -> MagicMock:
    runner = MagicMock(spec=RuneRunner)
    runner.emit_chain = AsyncMock(side_effect=lambda hook, initial: initial)
    runner.is_skill_catalog_suppressed = MagicMock(return_value=suppressed)
    runner.get_skill_catalog = MagicMock(return_value=catalog)
    return runner


def _assembly(**overrides: object) -> PromptAssembly:
    kwargs: dict[str, object] = {
        "base_prompt": "Base prompt.",
        "agent_name": "test-agent",
        "config_dir": "/cfg/test-agent",
        "custom_prompt": "",
        "runner": None,
    }
    kwargs.update(overrides)
    return PromptAssembly(**kwargs)  # type: ignore[arg-type]


class TestAssemble:
    @pytest.mark.asyncio
    async def test_without_runner_returns_base_prompt(self) -> None:
        assembly = _assembly(base_prompt="You are Mvge.")

        assert await assembly.assemble() == "You are Mvge."

    @pytest.mark.asyncio
    async def test_emits_before_mvge_start_once(self) -> None:
        runner = _mock_runner()
        assembly = _assembly(runner=runner)

        await assembly.assemble()

        runner.emit_chain.assert_awaited_once()
        call_args = runner.emit_chain.await_args.args
        assert call_args[0] == SigilHook.BEFORE_MVGE_START

    @pytest.mark.asyncio
    async def test_sigil_payload_carries_agent_inputs(self) -> None:
        runner = _mock_runner()
        assembly = _assembly(
            runner=runner,
            custom_prompt="Custom body",
            spell_names=["bash", "read"],
            cwd="/proj",
        )

        await assembly.assemble()

        payload = runner.emit_chain.await_args.args[1]
        assert payload["base_prompt"] == "Base prompt."
        assert payload["spell_names"] == ["bash", "read"]
        assert payload["config_dir"] == "/cfg/test-agent"
        assert payload["custom_prompt"] == "Custom body"
        assert payload["agent_name"] == "test-agent"
        assert payload["cwd"] == "/proj"

    @pytest.mark.asyncio
    async def test_default_cwd_is_process_cwd(self) -> None:
        runner = _mock_runner()
        assembly = _assembly(runner=runner)

        await assembly.assemble()

        payload = runner.emit_chain.await_args.args[1]
        assert payload["cwd"] == str(Path.cwd())

    @pytest.mark.asyncio
    async def test_config_dir_accepts_path(self) -> None:
        runner = _mock_runner()
        assembly = _assembly(runner=runner, config_dir=Path("/cfg/agent"))

        await assembly.assemble()

        payload = runner.emit_chain.await_args.args[1]
        assert payload["config_dir"] == str(Path("/cfg/agent"))

    @pytest.mark.asyncio
    async def test_runner_can_modify_base_prompt(self) -> None:

        async def injector(hook: SigilHook, data: Any) -> Any:
            assert isinstance(data, BeforeMvgeStartData)
            data.base_prompt = "Runes were here."
            return data

        runner = _mock_runner()
        runner.emit_chain = AsyncMock(side_effect=injector)
        assembly = _assembly(runner=runner)

        assert await assembly.assemble() == "Runes were here."

    @pytest.mark.asyncio
    async def test_typed_sigil_data_is_supported(self) -> None:
        modified = BeforeMvgeStartData(
            base_prompt="Typed prompt.",
            spell_names=[],
            config_dir="/cfg/test-agent",
            custom_prompt="",
            agent_name="test-agent",
            cwd="/proj",
        )
        runner = _mock_runner()
        runner.emit_chain = AsyncMock(return_value=modified)
        assembly = _assembly(runner=runner)

        assert await assembly.assemble() == "Typed prompt."

    @pytest.mark.asyncio
    async def test_missing_base_prompt_falls_back_to_original(self) -> None:
        runner = _mock_runner()
        runner.emit_chain = AsyncMock(return_value={})
        assembly = _assembly(base_prompt="Original.", runner=runner)

        assert await assembly.assemble() == "Original."

    @pytest.mark.asyncio
    async def test_skill_catalog_appended(self) -> None:
        runner = _mock_runner(catalog="## Available Skills\n\n### demo")
        assembly = _assembly(base_prompt="Body.", runner=runner)

        result = await assembly.assemble()

        assert result == "Body.\n\n## Available Skills\n\n### demo"

    @pytest.mark.asyncio
    async def test_suppressed_catalog_not_appended(self) -> None:
        runner = _mock_runner(suppressed=True, catalog="## Available Skills")
        assembly = _assembly(base_prompt="Body.", runner=runner)

        assert await assembly.assemble() == "Body."

    @pytest.mark.asyncio
    async def test_empty_catalog_not_appended(self) -> None:
        runner = _mock_runner(catalog="")
        assembly = _assembly(base_prompt="Body.", runner=runner)

        assert await assembly.assemble() == "Body."


class TestRender:
    def test_render_matches_shared_renderer(self) -> None:
        assembly = _assembly(cwd="/proj")

        result = assembly.render("Body.", ["bash"], ["Be concise."])

        assert result == _render_prompt(
            body="Body.",
            spells=["bash"],
            guidelines=["Be concise."],
            cwd="/proj",
        )
        assert "Active spells:" in result
        assert "Guidelines:" in result
        assert "Working Directory: /proj" in result

    def test_render_defaults_cwd_to_process_cwd(self) -> None:
        assembly = _assembly()

        result = assembly.render("Body.", [], [])

        assert f"Working Directory: {Path.cwd()}" in result

    def test_render_accepts_tuple_sequences(self) -> None:
        assembly = _assembly(cwd="/proj")

        result = assembly.render("Body.", ("bash",), ("Rule",))

        assert "  - bash" in result
        assert "- Rule" in result
