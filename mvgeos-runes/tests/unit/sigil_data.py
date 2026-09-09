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
    ResourcesDiscoverData,
    SessionBeforeForkData,
    SessionBeforeSwitchData,
    SessionShutdownData,
    SessionStartData,
    ShouldStopAfterTurnData,
    SigilHook,
    TurnEndData,
    TurnStartData,
    create_sigil_data,
)


class TestSigilDataClasses:
    """Test that all sigil data classes can be instantiated."""

    def test_before_invocation_data(self) -> None:
        data = BeforeInvocationData(invocation={"role": "user", "content": "test"})
        assert data.invocation == {"role": "user", "content": "test"}

    def test_after_invocation_data(self) -> None:
        data = AfterInvocationData(
            invocation={"role": "assistant", "content": "response"},
            stop_reason="stop",
        )
        assert data.invocation == {"role": "assistant", "content": "response"}
        assert data.stop_reason == "stop"

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

    def test_resources_discover_data(self) -> None:
        data = ResourcesDiscoverData(
            cwd="/test",
            reason="startup",
            skill_paths=["/skills/a"],
            prompt_paths=["/prompts/p.md"],
        )
        assert data.cwd == "/test"
        assert data.reason == "startup"
        assert data.skill_paths == ["/skills/a"]
        assert data.prompt_paths == ["/prompts/p.md"]


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

    def test_creates_resources_discover_data_from_dict(self) -> None:
        raw = {"cwd": "/workspace", "reason": "startup", "skill_paths": ["/skills"]}
        typed = create_sigil_data(SigilHook.RESOURCES_DISCOVER, raw)
        assert isinstance(typed, ResourcesDiscoverData)
        assert typed.cwd == "/workspace"
        assert typed.skill_paths == ["/skills"]
