from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_agent.constants import DEFAULT_MODEL
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeResponse,
    MvgeState,
    StopReason,
)
from mvgeos_runes.types import (
    SpellDefinition,
)

from coding_mvge.mvge import (
    DEFAULT_SPELL_MAP,
    CodingMvge,
)


@pytest.fixture
def agent() -> CodingMvge:
    return CodingMvge(api_key="test-key")


class _MockRealm:
    def __init__(self) -> None:
        self.close: Any = AsyncMock()

    def stream(self, *args: object, **kwargs: object) -> object:
        return _Iter()


def _make_mock_realm(text: str = "Hello") -> _MockRealm:
    return _MockRealm()


def _install_mock(agent: CodingMvge, text: str = "Hello") -> _MockRealm:
    from mvgeos_provider.types import Model

    mock_realm = _make_mock_realm(text)
    agent._realm = mock_realm  # type: ignore[assignment]
    agent._model = Model(
        id="test-model",
        name="Test",
        realm="test",
        base_url="",
        api_key="test-key",
    )
    mock_session = MagicMock()
    mock_session.start = AsyncMock()
    mock_session.shutdown = AsyncMock()
    mock_session.active_leaf_id_async = AsyncMock(return_value=None)
    mock_session.record_message_async = AsyncMock(return_value=None)
    agent._agent_tome = mock_session
    agent._state = MvgeState(
        system_prompt="test",
        model={"id": "test-model", "name": "Test"},
        contemplation_level=ContemplationLevel.OFF,
        spells=[],
        invocations=[],
        rune_runner=None,
        agent_tome=agent._agent_tome,
    )
    from mvgeos_agent.harness import MvgeHarness
    from mvgeos_agent.mvge_loop import MvgeLoop

    agent._loop = MvgeLoop(agent._state)
    agent._harness = MvgeHarness(agent._loop)
    agent._initialized = True
    return mock_realm


class _Iter:
    def __aiter__(self) -> object:
        from mvgeos_provider.types import Model, RealmResponse

        model = Model(
            id="test-model",
            name="Test",
            realm="test",
            base_url="",
            api_key="",
        )

        async def gen() -> object:
            yield RealmResponse(
                model=model,
                invocation=MvgeResponse(
                    role="assistant",
                    content=[{"type": "text", "text": "Hello"}],
                    stop_reason=StopReason.STOP,
                ),
            )

        return gen()


class TestCodingMvgeInit:
    def test_stores_config(self) -> None:
        env = MvgeEnvironment.resolve(
            "test-agent",
            overrides={
                "model": "test-model",
                "temperature": 0.5,
                "max_tokens": 2048,
                "contemplation_level": "high",
            },
            custom_prompt="Custom prompt",
        )
        agent = CodingMvge(
            api_key="k",
            spells=["bash", "read"],
            custom_system_prompt="Custom prompt",
            environment=env,
        )
        assert agent._api_key == "k"
        assert agent._model_id == "test-model"
        assert agent._spell_names == ["bash", "read"]
        assert agent._custom_system_prompt == "Custom prompt"
        assert agent._temperature == 0.5
        assert agent._max_tokens == 2048
        assert agent._contemplation_level == "high"

    def test_defaults(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent._model_id == DEFAULT_MODEL
        assert agent._spell_names == list(DEFAULT_SPELL_MAP)
        assert agent._custom_system_prompt == ""
        assert agent._temperature == 0.7
        assert agent._max_tokens == 4096
        assert agent._contemplation_level == "medium"

    def test_default_tome_dir(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent._tome_dir == Path.home() / ".agents" / ".mvgeos" / "tomes"


class TestCodingMvgeBuildSpells:
    def test_build_spells_returns_builtin_when_no_rune_runner(
        self, agent: CodingMvge
    ) -> None:
        # Without rune runner, builtin spells are returned by default (7 spells)
        spells = agent._build_spells()
        assert len(spells) == 7

    def test_build_spells_returns_active_set_spells(self, agent: CodingMvge) -> None:
        # _build_spells is driven by the runner's active-spell set, not a
        # hardcoded name tuple. Spells outside the active set are excluded.
        mock_runner = MagicMock()
        mock_runner.get_all_registered_spells.return_value = [
            SpellDefinition(
                name="tool_search", description="Search for tools", parameters={}
            ),
            SpellDefinition(
                name="skill_search", description="Search for skills", parameters={}
            ),
            SpellDefinition(
                name="bash", description="Execute shell commands", parameters={}
            ),
        ]
        # Only the active set is surfaced to the model.
        mock_runner.get_active_spells.return_value = ["tool_search", "skill_search"]
        agent._runner = mock_runner
        spells = agent._build_spells()
        rune_names = {s.name for s in spells if s.name not in DEFAULT_SPELL_MAP}
        assert rune_names == {"tool_search", "skill_search"}
        # A registered-but-inactive rune spell is not surfaced.
        assert "bash" not in rune_names

    def test_build_spells_excludes_inactive_rune_spells(
        self, agent: CodingMvge
    ) -> None:
        mock_runner = MagicMock()
        mock_runner.get_all_registered_spells.return_value = [
            SpellDefinition(name="a", description="", parameters={}),
            SpellDefinition(name="b", description="", parameters={}),
        ]
        mock_runner.get_active_spells.return_value = ["a"]
        agent._runner = mock_runner
        spells = agent._build_spells()
        rune_names = {s.name for s in spells if s.name not in DEFAULT_SPELL_MAP}
        assert rune_names == {"a"}

    def test_build_spells_empty(self, agent: CodingMvge) -> None:
        agent._spell_names = []
        spells = agent._build_spells()
        assert len(spells) == 0

    def test_render_prompt_lists_active_spells(self, agent: CodingMvge) -> None:
        mock_runner = MagicMock()
        mock_runner.get_active_spells.return_value = ["tool_search", "skill_search"]
        agent._runner = mock_runner
        prompt = agent._render_prompt("You are Mvge", [], [])
        assert "Active spells:" in prompt
        assert "tool_search" in prompt
        assert "skill_search" in prompt


class TestCodingMvgeProperties:
    def test_tome_id_none_before_init(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent.tome_id is None

    def test_enabled_spells(self) -> None:
        agent = CodingMvge(api_key="k", spells=["bash", "grep"])
        assert agent.enabled_spells == ["bash", "grep"]

    def test_registered_commands_empty(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent.registered_commands == []

    def test_registered_shortcuts_empty(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent.registered_shortcuts == []

    def test_registered_providers_empty(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent.registered_providers == []


class TestCodingMvgeRun:
    @pytest.mark.asyncio
    async def test_initialize_then_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            _install_mock(agent)

            result = await agent.run("Hi")
            assert result is not None
            await agent.close()

    @pytest.mark.asyncio
    async def test_raises_on_unknown_model(self) -> None:
        env = MvgeEnvironment.resolve(
            "test-agent", overrides={"model": "unknown/model"}
        )
        agent = CodingMvge(
            api_key="test-key",
            spells=[],
            environment=env,
        )
        with pytest.raises(ValueError, match="Unknown model"):
            await agent.initialize()

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            _install_mock(agent)

            async with agent as a:
                result = await a.run("Hello from context manager")
                assert result is not None

    @pytest.mark.asyncio
    async def test_run_returns_mvge_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            _install_mock(agent)

            result = await agent.run("What is it?")
            assert isinstance(result, MvgeResponse)
            assert result.content == [{"type": "text", "text": "Hello"}]
            await agent.close()

    @pytest.mark.asyncio
    async def test_initialize_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            _install_mock(agent)
            await agent.initialize()
            assert agent._initialized
            await agent.initialize()
            assert agent._initialized
            await agent.close()

    @pytest.mark.asyncio
    async def test_run_with_spells(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=["bash", "read"],
            )
            _install_mock(agent)

            result = await agent.run("list files")
            assert result is not None
            await agent.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
            )
            mock = _install_mock(agent)
            await agent.run("test")
            await agent.close()

            assert not agent._initialized
            mock.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            _install_mock(agent)

            result1 = await agent.run("First prompt")
            assert result1 is not None

            result2 = await agent.run("Second prompt")
            assert result2 is not None

            assert agent._state is not None
            assert len(agent._state.invocations) >= 3
            await agent.close()

    @pytest.mark.asyncio
    async def test_multi_turn_state_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            _install_mock(agent)

            await agent.run("One")
            assert agent._state is not None
            count_after_first = len(agent._state.invocations)

            await agent.run("Two")
            count_after_second = len(agent._state.invocations)

            assert count_after_second > count_after_first
            await agent.close()


class TestCodingMvgeSwitchModel:
    @pytest.mark.asyncio
    async def test_switch_model_preserves_session(self) -> None:
        from mvgeos_provider.models import list_models

        target = next(
            m.id
            for m in list_models()
            if m.id != "nvidia/nemotron-3-ultra-550b-a55b:free"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            await agent.initialize()
            tome_before = agent.tome_id
            assert tome_before is not None

            await agent.switch_model(target)

            assert agent.tome_id == tome_before
            assert agent._model_id == target
            assert agent._model is not None
            assert agent._model.id == target
            assert agent._state is not None
            assert agent._state.model is not None
            assert agent._state.model["id"] == target
            await agent.close()

    @pytest.mark.asyncio
    async def test_switch_model_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            await agent.initialize()
            tome_before = agent.tome_id

            with pytest.raises(ValueError, match="Unknown model"):
                await agent.switch_model("unknown/model")

            assert agent.tome_id == tome_before
            assert agent._model_id == "unknown/model"
            assert agent._model is not None
            assert agent._model.id == DEFAULT_MODEL
            await agent.close()

    @pytest.mark.asyncio
    async def test_switch_model_same_model_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=[],
            )
            await agent.initialize()
            await agent.switch_model(DEFAULT_MODEL)
            assert agent._model_id == DEFAULT_MODEL
            await agent.close()

    @pytest.mark.asyncio
    async def test_switch_model_before_init(self) -> None:
        from mvgeos_provider.models import list_models

        target = next(m.id for m in list_models() if m.id != DEFAULT_MODEL)
        agent = CodingMvge(api_key="test-key")
        await agent.switch_model(target)
        assert agent._model_id == target


class TestCodingMvgeToolCalls:
    @pytest.mark.asyncio
    async def test_agent_executes_spell_and_continues_turn(self) -> None:
        from mvgeos_agent.types import SpellResultMessage, StopReason
        from mvgeos_provider.types import RealmResponse

        from coding_mvge.mvge import _BuiltinSpell
        from coding_mvge.spells import cast_bash

        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=["bash"],
            )
            _install_mock(agent)
            assert agent._state is not None
            # Manually add the bash spell to the state
            agent._state.spells = [_BuiltinSpell("bash", cast_bash)]

            class FakeRealm:
                def __init__(self) -> None:
                    self.calls = 0

                async def close(self) -> None:
                    pass

                async def stream(
                    self,
                    model: object,
                    invocations: object,
                    config: object,
                    signal: object = None,
                ) -> object:
                    self.calls += 1
                    if self.calls == 1:
                        yield RealmResponse(
                            model=model,  # type: ignore[arg-type]
                            invocation=MvgeResponse(
                                role="assistant",
                                content=[
                                    {
                                        "type": "tool_call",
                                        "tool_call": {
                                            "id": "call-1",
                                            "name": "bash",
                                            "arguments": {"command": "echo hi"},
                                        },
                                    }
                                ],
                                stop_reason=StopReason.SPELL_USE,
                            ),
                        )
                    else:
                        yield RealmResponse(
                            model=model,  # type: ignore[arg-type]
                            invocation=MvgeResponse(
                                role="assistant",
                                content=[{"type": "text", "text": "done"}],
                                stop_reason=StopReason.STOP,
                            ),
                        )

            agent._realm = FakeRealm()  # type: ignore[assignment]

            result = await agent.run("run echo")

            assert isinstance(result, MvgeResponse)
            assert result.content == [{"type": "text", "text": "done"}]
            assert agent._state is not None
            assert any(
                isinstance(inv, SpellResultMessage) for inv in agent._state.invocations
            )
            await agent.close()

    @pytest.mark.asyncio
    async def test_make_stream_sends_tools_schema(self) -> None:

        from coding_mvge.mvge import _BuiltinSpell
        from coding_mvge.spells import cast_bash, cast_read

        with tempfile.TemporaryDirectory() as tmpdir:
            agent = CodingMvge(
                api_key="test-key",
                tome_dir=Path(tmpdir),
                spells=["bash", "read"],
            )
            _install_mock(agent)
            assert agent._state is not None
            # Manually add spell
            agent._state.spells = [
                _BuiltinSpell("bash", cast_bash),
                _BuiltinSpell("read", cast_read),
            ]

            captured: dict[str, Any] = {}

            class CaptureRealm:
                async def close(self) -> None:
                    pass

                async def stream(
                    self,
                    model: object,
                    invocations: object,
                    config: object,
                    signal: object = None,
                ) -> object:
                    captured["tools"] = config.tools  # type: ignore[attr-defined]
                    if len(captured["tools"]) < 0:
                        yield

            agent._realm = CaptureRealm()  # type: ignore[assignment]
            stream_fn = agent._make_stream_fn(
                agent._model,  # type: ignore[arg-type]
                agent._realm,  # type: ignore[arg-type]
                agent._state,
                0.7,
                4096,
            )

            async for _ in stream_fn(agent._state.invocations):
                pass

            assert captured.get("tools")
            names = [t["function"]["name"] for t in captured["tools"]]
            assert names == ["bash", "read"]
            props = captured["tools"][0]["function"]["parameters"]["properties"]
            assert "command" in props

    @pytest.mark.asyncio
    async def test_builtin_spell_executes_real_function(self) -> None:
        from coding_mvge.mvge import _BuiltinSpell
        from coding_mvge.spells import cast_bash

        bash_spell = _BuiltinSpell("bash", cast_bash)
        assert bash_spell.parameters.get("properties", {}).get("command")

        result = await bash_spell.execute(
            "call-1", {"command": "echo hi", "timeout_ms": 15000}
        )
        assert "hi" in result


class TestBuildSystemPrompt:
    def test_hardcoded_fallback(self) -> None:
        env = MvgeEnvironment.resolve("test-agent", allow_unknown_agent=True)
        prompt = env.render(spells=["bash", "read"])
        assert "You are Mvge" in prompt
        assert "Active spells:" in prompt
        assert "bash" in prompt
        assert "read" in prompt

    def test_config_dir_does_not_exist(self) -> None:
        env = MvgeEnvironment.resolve("test-agent", allow_unknown_agent=True)
        prompt = env.render(spells=["bash"])
        assert "You are Mvge" in prompt

    def test_custom_prompt_overrides_base(self) -> None:
        env = MvgeEnvironment.resolve(
            "test-agent",
            custom_prompt="Custom agent prompt here.",
            allow_unknown_agent=True,
        )
        prompt = env.render()
        assert "Custom agent prompt here." in prompt
        assert "You are Mvge" not in prompt

    def test_system_md_loads(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "SYSTEM.md").write_text("Loaded from file.", encoding="utf-8")
            env = MvgeEnvironment.resolve(
                "test-agent", config_dir=config_dir, allow_unknown_agent=True
            )
            prompt = env.render()
            assert "Loaded from file." in prompt
            assert "You are Mvge" not in prompt

    def test_guidelines_md_loads(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "GUIDELINES.md").write_text(
                "- Rule one\n- Rule two\n", encoding="utf-8"
            )
            env = MvgeEnvironment.resolve(
                "test-agent", config_dir=config_dir, allow_unknown_agent=True
            )
            prompt = env.render()
            assert "Rule one" in prompt
            assert "Rule two" in prompt
            assert "Be concise" not in prompt

    def test_both_files_load(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "SYSTEM.md").write_text("File-based agent.", encoding="utf-8")
            (config_dir / "GUIDELINES.md").write_text(
                "- Custom rule\n", encoding="utf-8"
            )
            env = MvgeEnvironment.resolve(
                "test-agent", config_dir=config_dir, allow_unknown_agent=True
            )
            prompt = env.render()
            assert "File-based agent." in prompt
            assert "Custom rule" in prompt
            assert "Be concise" not in prompt


class TestCodingMvgeConfig:
    def test_default_name(self) -> None:
        agent = CodingMvge(api_key="k")
        assert agent._name == "default-mvge"

    def test_custom_name(self) -> None:
        agent = CodingMvge(api_key="k", name="my-agent")
        assert agent._name == "my-agent"

    def test_config_dir_uses_name(self) -> None:
        agent = CodingMvge(api_key="k", name="custom-agent")
        assert "custom-agent" in str(agent.config_dir)
