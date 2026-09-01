from __future__ import annotations

from mvgeos_runes.types import (
    AfterInvocationData,
    AfterProviderResponseData,
    AfterSpellResultData,
    AgentEndData,
    AgentStartData,
    BeforeInvocationData,
    BeforeMvgeStartData,
    BeforeProviderHeadersData,
    BeforeProviderRequestData,
    BeforeSpellCastData,
    CompactionEndData,
    CompactionStartData,
    ContextTransformData,
    InputData,
    PrepareNextTurnData,
    SessionBeforeCompactData,
    SessionBeforeForkData,
    SessionBeforeSwitchData,
    SessionShutdownData,
    SessionStartData,
    ShouldStopAfterTurnData,
    SigilHook,
    TurnEndData,
    TurnStartData,
    create_sigil_data,
    get_sigil_data_class,
)


class TestSigilDataClasses:
    """Test that all sigil data classes can be instantiated
    and support dict-like access."""

    def test_before_invocation_data(self) -> None:
        data = BeforeInvocationData(invocation={"role": "user", "content": "test"})
        assert data.invocation == {"role": "user", "content": "test"}
        # Test dict-like access
        assert data["invocation"] == {"role": "user", "content": "test"}
        assert "invocation" in data
        assert data.get("invocation") == {"role": "user", "content": "test"}
        assert data.get("nonexistent", "default") == "default"

    def test_after_invocation_data(self) -> None:
        data = AfterInvocationData(
            invocation={"role": "assistant", "content": "response"},
            stop_reason="stop",
        )
        assert data.invocation == {"role": "assistant", "content": "response"}
        assert data.stop_reason == "stop"
        assert data["stop_reason"] == "stop"

    def test_before_spell_cast_data(self) -> None:
        data = BeforeSpellCastData(
            spell_cast={
                "id": "123",
                "name": "read_file",
                "arguments": {"path": "test.py"},
            },
            spell_name="read_file",
        )
        assert data.spell_cast["name"] == "read_file"
        assert data.spell_name == "read_file"
        assert data["spell_name"] == "read_file"
        assert data["spell_cast"]["id"] == "123"

    def test_after_spell_result_data(self) -> None:
        data = AfterSpellResultData(
            spell_name="read_file",
            spell_cast_id="123",
            result="file content",
        )
        assert data.spell_name == "read_file"
        assert data.spell_cast_id == "123"
        assert data.result == "file content"

    def test_before_provider_request_data(self) -> None:
        data = BeforeProviderRequestData(model={"id": "model-1", "name": "Model"})
        assert data.model["id"] == "model-1"

    def test_after_provider_response_data(self) -> None:
        data = AfterProviderResponseData(
            response={"content": "response"},
            mana_used=100,
        )
        assert data.response["content"] == "response"
        assert data.mana_used == 100

    def test_before_provider_headers_data(self) -> None:
        data = BeforeProviderHeadersData(headers={"Authorization": "Bearer token"})
        assert data.headers["Authorization"] == "Bearer token"

    def test_turn_start_data(self) -> None:
        data = TurnStartData(model={"id": "model-1"})
        assert data.model["id"] == "model-1"

    def test_turn_end_data(self) -> None:
        data = TurnEndData(stop_reason="stop", mana_used=50)
        assert data.stop_reason == "stop"
        assert data.mana_used == 50

    def test_session_start_data(self) -> None:
        data = SessionStartData(session_name="test-session")
        assert data.session_name == "test-session"

    def test_session_shutdown_data(self) -> None:
        data = SessionShutdownData(session_name="test-session")
        assert data.session_name == "test-session"

    def test_session_before_switch_data(self) -> None:
        data = SessionBeforeSwitchData(from_session="session1", to_session="session2")
        assert data.from_session == "session1"
        assert data.to_session == "session2"

    def test_session_before_fork_data(self) -> None:
        data = SessionBeforeForkData(parent_session="parent", child_session="child")
        assert data.parent_session == "parent"
        assert data.child_session == "child"

    def test_session_before_compact_data(self) -> None:
        data = SessionBeforeCompactData(session_name="test-session")
        assert data.session_name == "test-session"

    def test_compaction_start_data(self) -> None:
        data = CompactionStartData(session_name="test-session", message_count=100)
        assert data.session_name == "test-session"
        assert data.message_count == 100

    def test_compaction_end_data(self) -> None:
        data = CompactionEndData(
            session_name="test-session",
            original_count=100,
            compacted_count=20,
        )
        assert data.original_count == 100
        assert data.compacted_count == 20

    def test_context_transform_data(self) -> None:
        data = ContextTransformData(invocations=[{"role": "user", "content": "test"}])
        assert len(data.invocations) == 1

    def test_agent_start_data(self) -> None:
        data = AgentStartData()
        assert isinstance(data, AgentStartData)

    def test_agent_end_data(self) -> None:
        data = AgentEndData(stop_reason="stop")
        assert data.stop_reason == "stop"

    def test_before_mvge_start_data(self) -> None:
        data = BeforeMvgeStartData(
            base_prompt="base prompt",
            spell_names=["spell1", "spell2"],
            config_dir="/config",
            custom_prompt="custom",
            agent_name="test-agent",
            cwd="/cwd",
        )
        assert data.base_prompt == "base prompt"
        assert data.spell_names == ["spell1", "spell2"]
        assert data.agent_name == "test-agent"

    def test_input_data(self) -> None:
        data = InputData(content="user input")
        assert data.content == "user input"

        # Test with list content
        data2 = InputData(content=[{"type": "text", "text": "multi"}])
        assert data2.content == [{"type": "text", "text": "multi"}]

    def test_should_stop_after_turn_data(self) -> None:
        data = ShouldStopAfterTurnData()
        assert isinstance(data, ShouldStopAfterTurnData)

    def test_prepare_next_turn_data(self) -> None:
        data = PrepareNextTurnData(
            system_prompt="sys prompt",
            max_turns=10,
            temperature=0.7,
        )
        assert data.system_prompt == "sys prompt"
        assert data.max_turns == 10
        assert data.temperature == 0.7


class TestCreateSigilData:
    """Test the create_sigil_data factory function."""

    def test_creates_typed_data_from_dict(self) -> None:
        raw = {"spell_name": "test", "spell_cast_id": "123", "result": "ok"}
        typed = create_sigil_data(SigilHook.AFTER_SPELL_RESULT, raw)
        assert isinstance(typed, AfterSpellResultData)
        assert typed.spell_name == "test"
        assert typed.spell_cast_id == "123"
        assert typed.result == "ok"

    def test_passes_through_already_typed_data(self) -> None:
        original = AfterSpellResultData(
            spell_name="test", spell_cast_id="123", result="ok"
        )
        typed = create_sigil_data(SigilHook.AFTER_SPELL_RESULT, original)
        assert typed is original

    def test_returns_raw_for_unknown_hook(self) -> None:
        raw = {"custom": "data"}
        result = create_sigil_data(SigilHook.INPUT, raw)  # INPUT has a data class
        # Should fall back to raw dict because content is missing
        assert result == raw

        # Test with a hook that has no data class (if any)
        class FakeHook:
            value = "fake_hook"

        result2 = create_sigil_data(FakeHook(), raw)  # type: ignore[arg-type]
        assert result2 is raw

    def test_falls_back_to_raw_on_construction_error(self) -> None:
        # Missing required field
        raw = {"spell_name": "test"}  # missing spell_cast_id and result
        typed = create_sigil_data(SigilHook.AFTER_SPELL_RESULT, raw)
        # Should fall back to raw dict
        assert typed == raw

    def test_handles_non_dict_data(self) -> None:
        data = "not a dict"
        result = create_sigil_data(SigilHook.AFTER_SPELL_RESULT, data)
        assert result == "not a dict"


class TestGetSigilDataClass:
    """Test the get_sigil_data_class function."""

    def test_returns_correct_class_for_each_hook(self) -> None:
        assert get_sigil_data_class(SigilHook.BEFORE_INVOCATION) == BeforeInvocationData
        assert get_sigil_data_class(SigilHook.AFTER_INVOCATION) == AfterInvocationData
        assert get_sigil_data_class(SigilHook.BEFORE_SPELL_CAST) == BeforeSpellCastData
        assert (
            get_sigil_data_class(SigilHook.AFTER_SPELL_RESULT) == AfterSpellResultData
        )
        assert (
            get_sigil_data_class(SigilHook.BEFORE_PROVIDER_REQUEST)
            == BeforeProviderRequestData
        )
        assert (
            get_sigil_data_class(SigilHook.AFTER_PROVIDER_RESPONSE)
            == AfterProviderResponseData
        )
        assert (
            get_sigil_data_class(SigilHook.BEFORE_PROVIDER_HEADERS)
            == BeforeProviderHeadersData
        )
        assert get_sigil_data_class(SigilHook.TURN_START) == TurnStartData
        assert get_sigil_data_class(SigilHook.TURN_END) == TurnEndData
        assert get_sigil_data_class(SigilHook.SESSION_START) == SessionStartData
        assert get_sigil_data_class(SigilHook.SESSION_SHUTDOWN) == SessionShutdownData
        assert (
            get_sigil_data_class(SigilHook.SESSION_BEFORE_SWITCH)
            == SessionBeforeSwitchData
        )
        assert (
            get_sigil_data_class(SigilHook.SESSION_BEFORE_FORK) == SessionBeforeForkData
        )
        assert (
            get_sigil_data_class(SigilHook.SESSION_BEFORE_COMPACT)
            == SessionBeforeCompactData
        )
        assert get_sigil_data_class(SigilHook.COMPACTION_START) == CompactionStartData
        assert get_sigil_data_class(SigilHook.COMPACTION_END) == CompactionEndData
        assert get_sigil_data_class(SigilHook.CONTEXT_TRANSFORM) == ContextTransformData
        assert get_sigil_data_class(SigilHook.AGENT_START) == AgentStartData
        assert get_sigil_data_class(SigilHook.AGENT_END) == AgentEndData
        assert get_sigil_data_class(SigilHook.BEFORE_MVGE_START) == BeforeMvgeStartData
        assert get_sigil_data_class(SigilHook.INPUT) == InputData
        assert (
            get_sigil_data_class(SigilHook.SHOULD_STOP_AFTER_TURN)
            == ShouldStopAfterTurnData
        )
        assert get_sigil_data_class(SigilHook.PREPARE_NEXT_TURN) == PrepareNextTurnData


class TestSigilDataDictMethods:
    """Test dict-like methods on sigil data classes."""

    def test_keys_method(self) -> None:
        data = BeforeSpellCastData(spell_cast={"name": "test"}, spell_name="test")
        keys = data.keys()
        assert "spell_cast" in keys
        assert "spell_name" in keys

    def test_items_method(self) -> None:
        data = TurnEndData(stop_reason="stop", mana_used=100)
        items = data.items()
        assert ("stop_reason", "stop") in items
        assert ("mana_used", 100) in items

    def test_values_method(self) -> None:
        data = SessionStartData(session_name="test")
        values = data.values()
        assert "test" in values

    def test_to_dict_method(self) -> None:
        data = AgentEndData(stop_reason="length")
        d = data.to_dict()
        assert d == {"stop_reason": "length"}

    def test_contains_method(self) -> None:
        data = InputData(content="test")
        assert "content" in data
        assert "nonexistent" not in data

    def test_get_method_with_default(self) -> None:
        data = BeforeMvgeStartData(
            base_prompt="base",
            spell_names=[],
            config_dir="",
            custom_prompt="",
            agent_name="agent",
            cwd="",
        )
        assert data.get("base_prompt") == "base"
        assert data.get("nonexistent", "default") == "default"
