from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mvgeos_core.abort import AbortSignal
from mvgeos_core.events import QueueMode
from mvgeos_core.spells import ExecutionMode
from mvgeos_runes.types import SpellDefinition

from mvgeos_agent import Mvge
from mvgeos_agent.mvge import _validate_spell_name


def dummy_built_in(command: str) -> str:
    """Built-in command."""
    return command


class ValidRuneSpell(SpellDefinition):
    def __init__(
        self,
        name: str = "valid_spell",
        parameters: dict[str, Any] | None = None,
        source_rune: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            description="A valid spell",
            parameters=parameters or {},
            execution_mode=ExecutionMode.PARALLEL,
            source_rune=source_rune,
        )

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return {"result": "ok"}


class ValidSpellWithoutOnUpdate(SpellDefinition):
    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
    ) -> dict[str, Any]:
        return {"result": "ok"}


class ValidSpellWithKwargs(SpellDefinition):
    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {"result": "ok"}


class ValidSpellWithArgsKwargs(SpellDefinition):
    async def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"result": "ok"}


class SpellMissingExecute:
    def __init__(self, name: str, parameters: dict[str, Any] | None = None) -> None:
        self.name = name
        self.parameters = parameters or {}


class SpellNonCallableExecute(SpellDefinition):
    execute = "not_a_callable"  # type: ignore[assignment]


class SpellZeroArgExecute(SpellDefinition):
    async def execute(self) -> dict[str, Any]:  # type: ignore[override]
        return {}


class SpellPositionalOnlyTwoArgs(SpellDefinition):
    async def execute(  # type: ignore[override]
        self, spell_cast_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return {}


class SpellExtraRequiredArg(SpellDefinition):
    async def execute(  # type: ignore[override]
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        extra_required: str,
        signal: AbortSignal | None = None,
    ) -> dict[str, Any]:
        return {}


def _create_mock_runner(spells: list[SpellDefinition]) -> MagicMock:
    runner = MagicMock()
    runner.get_all_registered_spells.return_value = spells
    runner.get_active_spells.return_value = [s.name for s in spells]
    return runner


class TestMvgeBuildSpellsValidation:
    def test_build_spells_with_valid_rune_spells(self) -> None:
        agent = Mvge(api_key="k", spells=[dummy_built_in])
        spell_1 = ValidRuneSpell("rune_tool_1", parameters={})
        spell_2 = ValidRuneSpell(
            "rune_tool_2",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        agent._runner = _create_mock_runner([spell_1, spell_2])

        spells = agent._build_spells()
        names = [s.name for s in spells]
        assert "dummy_built_in" in names
        assert "rune_tool_1" in names
        assert "rune_tool_2" in names

    def test_build_spells_accepts_valid_signature_variants(self) -> None:
        agent = Mvge(api_key="k", spells=[])
        s1 = ValidSpellWithoutOnUpdate("s1", {})
        s2 = ValidSpellWithKwargs("s2", {})
        s3 = ValidSpellWithArgsKwargs("s3", {})
        agent._runner = _create_mock_runner([s1, s2, s3])

        spells = agent._build_spells()
        names = [s.name for s in spells]
        assert names == ["s1", "s2", "s3"]

    def test_rejects_non_dict_parameter_schema(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[])
        s1 = ValidRuneSpell("s1")
        s1.parameters = "not_a_dict"  # type: ignore[assignment]
        s2 = ValidRuneSpell("s2")
        s2.parameters = [1, 2, 3]  # type: ignore[assignment]
        s3 = ValidRuneSpell("s3")
        s3.parameters = 123  # type: ignore[assignment]
        s4 = ValidRuneSpell("s4")
        s4.parameters = None  # type: ignore[assignment]
        agent._runner = _create_mock_runner([s1, s2, s3, s4])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        assert len(spells) == 0
        assert "Rune spell 's1' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's2' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's3' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's4' has an invalid parameter schema" in caplog.text

    def test_rejects_malformed_json_schema_structure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[])
        # Bad type (not 'object')
        s1 = ValidRuneSpell("s1", parameters={"type": "string"})
        # Bad properties (not a dict)
        s2 = ValidRuneSpell("s2", parameters={"properties": "invalid"})
        # Bad property definition (not a dict)
        s3 = ValidRuneSpell("s3", parameters={"properties": {"x": "not_a_dict"}})
        # Bad required (not a list/sequence)
        s4 = ValidRuneSpell("s4", parameters={"required": "field"})
        # Bad required items (not strings)
        s5 = ValidRuneSpell("s5", parameters={"required": [123]})
        # Bad properties key (not a string)
        s6 = ValidRuneSpell("s6", parameters={"properties": {123: {}}})  # type: ignore[dict-item]

        agent._runner = _create_mock_runner([s1, s2, s3, s4, s5, s6])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        assert len(spells) == 0
        assert "Rune spell 's1' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's2' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's3' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's4' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's5' has an invalid parameter schema" in caplog.text
        assert "Rune spell 's6' has an invalid parameter schema" in caplog.text

    def test_rejects_incompatible_execute_signature(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[])
        s1 = SpellNonCallableExecute("s1", {})
        s2 = SpellZeroArgExecute("s2", {})
        s3 = SpellPositionalOnlyTwoArgs("s3", {})
        s4 = SpellExtraRequiredArg("s4", {})
        s5 = SpellMissingExecute("s5", {})

        agent._runner = _create_mock_runner([s1, s2, s3, s4, s5])  # type: ignore[list-item]

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        assert len(spells) == 0
        assert "Rune spell 's1' execution signature does not conform" in caplog.text
        assert "Rune spell 's2' execution signature does not conform" in caplog.text
        assert "Rune spell 's3' execution signature does not conform" in caplog.text
        assert "Rune spell 's4' execution signature does not conform" in caplog.text
        assert "Rune spell 's5' execution signature does not conform" in caplog.text

    def test_rejects_uninspectable_signature(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import patch

        agent = Mvge(api_key="k", spells=[])
        s1 = ValidRuneSpell("s1")
        agent._runner = _create_mock_runner([s1])

        with (
            patch("inspect.signature", side_effect=ValueError("Cannot inspect")),
            caplog.at_level(logging.WARNING),
        ):
            spells = agent._build_spells()

        assert len(spells) == 0
        assert "Rune spell 's1' execution signature does not conform" in caplog.text


class TestMvgeBuildSpellsCollisionHandling:
    def test_collision_with_builtin_spell_prefixes_rune_name(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[dummy_built_in])
        # dummy_built_in has name "dummy_built_in"
        colliding_rune_spell = ValidRuneSpell(
            name="dummy_built_in", source_rune="custom_rune"
        )
        agent._runner = _create_mock_runner([colliding_rune_spell])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        names = [s.name for s in spells]
        assert "dummy_built_in" in names
        assert "custom_rune_dummy_built_in" in names
        assert (
            "Rune spell 'dummy_built_in' collides with existing spell; "
            "renaming to 'custom_rune_dummy_built_in'." in caplog.text
        )

    def test_collision_without_source_rune_uses_rune_prefix(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[dummy_built_in])
        colliding_rune_spell = ValidRuneSpell(name="dummy_built_in", source_rune=None)
        agent._runner = _create_mock_runner([colliding_rune_spell])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        names = [s.name for s in spells]
        assert "dummy_built_in" in names
        assert "rune_dummy_built_in" in names
        assert (
            "Rune spell 'dummy_built_in' collides with existing spell; "
            "renaming to 'rune_dummy_built_in'." in caplog.text
        )

    def test_collision_between_two_rune_spells_prefixes_second(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[])
        s1 = ValidRuneSpell(name="find_items", source_rune="rune_one")
        s2 = ValidRuneSpell(name="find_items", source_rune="rune_two")
        agent._runner = _create_mock_runner([s1, s2])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        names = [s.name for s in spells]
        assert "find_items" in names
        assert "rune_two_find_items" in names
        assert (
            "Rune spell 'find_items' collides with existing spell; "
            "renaming to 'rune_two_find_items'." in caplog.text
        )

    def test_double_collision_skipped_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[])
        s0 = ValidRuneSpell(name="spell", source_rune="first")
        s1 = ValidRuneSpell(name="custom_rune_spell", source_rune="second")
        # s2 is "spell" with source_rune="custom_rune" -> would become
        # "custom_rune_spell" which collides with s1
        s2 = ValidRuneSpell(name="spell", source_rune="custom_rune")
        agent._runner = _create_mock_runner([s0, s1, s2])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        names = [s.name for s in spells]
        assert names == ["spell", "custom_rune_spell"]
        assert (
            "Prefixed rune spell 'custom_rune_spell' still collides with an "
            "existing spell and will be skipped." in caplog.text
        )

    def test_build_spells_idempotent_across_multiple_calls(self) -> None:
        agent = Mvge(api_key="k", spells=[dummy_built_in])
        colliding_rune_spell = ValidRuneSpell(
            name="dummy_built_in", source_rune="custom_rune"
        )
        agent._runner = _create_mock_runner([colliding_rune_spell])

        spells_1 = agent._build_spells()
        spells_2 = agent._build_spells()

        assert [s.name for s in spells_1] == [
            "dummy_built_in",
            "custom_rune_dummy_built_in",
        ]
        assert [s.name for s in spells_2] == [
            "dummy_built_in",
            "custom_rune_dummy_built_in",
        ]


class TestMvgeBuildSpellsNameValidation:
    def test_validate_spell_name_rules(self) -> None:
        assert _validate_spell_name("valid_name") is True
        assert _validate_spell_name("valid-name-123") is True
        assert _validate_spell_name("UPPER_case") is True
        assert _validate_spell_name("tool1") is True

        assert _validate_spell_name("invalid.name") is False
        assert _validate_spell_name("invalid name") is False
        assert _validate_spell_name("invalid/name") is False
        assert _validate_spell_name("") is False
        assert _validate_spell_name(None) is False
        assert _validate_spell_name(123) is False

    def test_rune_spell_with_invalid_name_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = Mvge(api_key="k", spells=[])
        bad_spell = ValidRuneSpell(name="knowledge_skill.consolidate")
        agent._runner = _create_mock_runner([bad_spell])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        assert len(spells) == 0
        assert (
            "Rune spell 'knowledge_skill.consolidate' has an invalid name"
            in caplog.text
        )

    def test_injected_spell_with_invalid_name_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def invalid_dot_spell() -> str:
            return "ok"

        invalid_dot_spell.__name__ = "invalid.spell.name"

        agent = Mvge(api_key="k", spells=[invalid_dot_spell])

        with caplog.at_level(logging.WARNING):
            spells = agent._build_spells()

        assert len(spells) == 0
        assert "Spell 'invalid.spell.name' has an invalid name" in caplog.text

    def test_make_stream_fn_passes_system_prompt_to_channel_config(self) -> None:
        from mvgeos_core.channel import Model

        from mvgeos_agent.types import MvgeState

        agent = Mvge(api_key="k", spells=[])
        model = Model(id="m", name="n", realm="r", base_url="", api_key="")
        mock_realm = MagicMock()
        mock_realm.stream.return_value = []
        state = MvgeState(system_prompt="Custom System Prompt with Skills")

        stream_fn = agent._make_stream_fn(
            model=model,
            realm=mock_realm,
            state=state,
            temperature=0.5,
            max_tokens=1000,
        )
        stream_fn([])

        assert mock_realm.stream.called
        call_config = mock_realm.stream.call_args.kwargs["config"]
        assert call_config.system_prompt == "Custom System Prompt with Skills"


class TestMvgeNoLongerOwnsTurnLoop:
    def test_make_stream_removed(self) -> None:
        assert not hasattr(Mvge, "_make_stream")


class TestMvgeQueueMode:
    def test_default_queue_mode_is_one_at_a_time(self) -> None:
        agent = Mvge(api_key="test-key")
        assert agent.queue_mode == QueueMode.ONE_AT_A_TIME

    def test_queue_mode_can_be_set_to_all(self) -> None:
        agent = Mvge(api_key="test-key")
        agent.queue_mode = QueueMode.ALL
        assert agent.queue_mode == QueueMode.ALL

    def test_queue_mode_accepts_string(self) -> None:
        agent = Mvge(api_key="test-key")
        agent.queue_mode = "one-at-a-time"
        assert agent.queue_mode == QueueMode.ONE_AT_A_TIME
        agent.queue_mode = "all"
        assert agent.queue_mode == QueueMode.ALL


class TestMvgePropertiesAndMethods:
    def test_basic_properties(self, tmp_path: Path) -> None:
        agent = Mvge(
            api_key="test-key",
            name="test_mvge",
            tome_dir=tmp_path / "sessions",
            spells=[],
        )
        assert agent.name == "test_mvge"
        assert agent.tome_dir == tmp_path / "sessions"
        assert agent.tome_id is None
        assert agent.mana_used is None
        assert isinstance(agent.config_dir, Path)
        assert agent.environment is not None
        assert isinstance(agent.spells, list)
        assert agent.event_bus is not None
        assert isinstance(agent.diagnostics, list)
        assert isinstance(agent.available_spells, list)
        assert isinstance(agent.registered_commands, list)
        assert isinstance(agent.registered_shortcuts, list)
        assert isinstance(agent.registered_providers, list)
        assert agent.model_registry is not None
        assert agent.model_id is not None
        assert agent.contemplation_level is not None

    def test_set_enabled_spells(self) -> None:
        agent = Mvge(api_key="test-key", spells=[dummy_built_in])
        assert "dummy_built_in" in agent.available_spells
        agent.set_enabled_spells(["dummy_built_in"])
        assert "dummy_built_in" in agent.enabled_spells
        agent.set_enabled_spells([])
        assert agent.enabled_spells == []

    def test_set_environment_and_config_manager(self) -> None:
        agent = Mvge(api_key="test-key", spells=[])
        env = agent.environment
        agent.set_environment(env)
        assert agent.environment == env
        agent.set_config_manager(None)
