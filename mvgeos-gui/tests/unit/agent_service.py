"""Unit tests for AgentService event sink and channeling bridge."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_agent.errors import AuthenticationError
from mvgeos_agent.types import MvgeEvent, MvgeEventType

from mvgeos_gui.agent_service import AgentService, resolve_api_key
from mvgeos_gui.models import ChatMessage, StepType, TaskStatus
from mvgeos_gui.state import AppState


@pytest.fixture
def app_state(tmp_path: Path) -> AppState:
    return AppState(project_path=tmp_path)


@pytest.fixture
def agent_service(tmp_path: Path) -> AgentService:
    return AgentService(project_path=tmp_path, api_key="test-api-key")


def test_agent_service_initialization(
    agent_service: AgentService, tmp_path: Path
) -> None:
    """Verify default properties of AgentService."""
    assert agent_service.project_path == tmp_path
    assert agent_service.is_running is False


def test_resolve_api_key_variants() -> None:
    """Verify API key resolution from explicit args, env, and auth file."""
    # 1. Explicit key
    assert resolve_api_key("sk-explicit") == "sk-explicit"

    # 2. OPENROUTER_API_KEY env var
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-env"}):
        assert resolve_api_key() == "sk-or-env"

    # 3. MVGEOS_API_KEY fallback env var
    with patch.dict(
        "os.environ", {"OPENROUTER_API_KEY": "", "MVGEOS_API_KEY": "sk-mvgeos-env"}
    ):
        assert resolve_api_key() == "sk-mvgeos-env"

    # 4. load_api_key_from_auth fallback
    with (
        patch.dict("os.environ", {"OPENROUTER_API_KEY": "", "MVGEOS_API_KEY": ""}),
        patch(
            "mvgeos_cli.auth.load_api_key_from_auth",
            return_value="sk-auth-file",
        ),
    ):
        assert resolve_api_key() == "sk-auth-file"

    # 5. None when no source is available
    with (
        patch.dict("os.environ", {"OPENROUTER_API_KEY": "", "MVGEOS_API_KEY": ""}),
        patch("mvgeos_cli.auth.load_api_key_from_auth", return_value=None),
    ):
        assert resolve_api_key() is None


def test_get_or_create_agent_with_factory(app_state: AppState) -> None:
    """Verify get_or_create_agent uses custom agent_factory if provided."""
    mock_agent = MagicMock()
    factory = MagicMock(return_value=mock_agent)
    service = AgentService(
        project_path=app_state.project_path,
        api_key="test-key",
        agent_factory=factory,
    )

    agent = service.get_or_create_agent(app_state)
    assert agent == mock_agent
    factory.assert_called_once_with(
        project_path=app_state.project_path,
        api_key=service._api_key,
        state=app_state,
    )
    # Subsequent call returns cached instance
    assert service.get_or_create_agent(app_state) == mock_agent
    assert factory.call_count == 1


@patch("coding_mvge.mvge.CodingMvge")
def test_get_or_create_agent_default(
    mock_coding_mvge: MagicMock, app_state: AppState
) -> None:
    """Verify get_or_create_agent instantiates default CodingMvge."""
    mock_instance = MagicMock()
    mock_coding_mvge.return_value = mock_instance
    service = AgentService(project_path=app_state.project_path, api_key="test-key")

    agent = service.get_or_create_agent(app_state)
    assert agent == mock_instance
    mock_coding_mvge.assert_called_once()


def test_handle_agent_start_event(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify AGENT_START initializes timing and streaming flags."""
    msg = ChatMessage(role="assistant", is_streaming=False)
    app_state.messages.append(msg)
    app_state.is_channeling = False

    event = MvgeEvent(type=MvgeEventType.AGENT_START, data={})
    agent_service.handle_event(event, msg, app_state)
    assert msg.is_streaming is True
    assert app_state.is_channeling is True


def test_handle_message_update_event(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify MESSAGE_UPDATE appends streamed tokens to ChatMessage content."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    event1 = MvgeEvent(type=MvgeEventType.MESSAGE_UPDATE, data={"text": "Hello"})
    agent_service.handle_event(event1, msg, app_state)
    assert msg.content == "Hello"

    event2 = MvgeEvent(type=MvgeEventType.MESSAGE_UPDATE, data={"text": " world!"})
    agent_service.handle_event(event2, msg, app_state)
    assert msg.content == "Hello world!"


def test_handle_message_update_contemplation(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify MESSAGE_UPDATE with kind=contemplation routes to msg.contemplation."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    event = MvgeEvent(
        type=MvgeEventType.MESSAGE_UPDATE,
        data={"text": "Thinking deeply...", "kind": "contemplation"},
    )
    agent_service.handle_event(event, msg, app_state)
    assert msg.contemplation == "Thinking deeply..."
    assert msg.content == ""


def test_handle_message_update_inline_think_tags(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify inline <think> tags are stripped from content to contemplation."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    event = MvgeEvent(
        type=MvgeEventType.MESSAGE_UPDATE,
        data={"text": "<think>Let me formulate response</think>Hello!"},
    )
    agent_service.handle_event(event, msg, app_state)
    assert msg.contemplation == "Let me formulate response"
    assert msg.content == "Hello!"


def test_extract_contemplation_tags_helper() -> None:
    """Verify extract_contemplation_tags splits closed and unclosed think tags."""
    from mvgeos_gui.models import extract_contemplation_tags

    # Closed tag
    cleaned, thought = extract_contemplation_tags(
        "<thought>Initial plan</thought>Actual output"
    )
    assert cleaned == "Actual output"
    assert thought == "Initial plan"

    # Multiple closed tags
    cleaned, thought = extract_contemplation_tags(
        "<think>Thought 1</think>Output<think>Thought 2</think>"
    )
    assert cleaned == "Output"
    assert thought == "Thought 1\n\nThought 2"

    # Plain text without tags
    cleaned, thought = extract_contemplation_tags("Just plain text")
    assert cleaned == "Just plain text"
    assert thought == ""


def test_handle_provider_response_mana_tracking(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify AFTER_PROVIDER_RESPONSE updates mana metrics."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    event = MvgeEvent(
        type=MvgeEventType.AFTER_PROVIDER_RESPONSE,
        data={"mana_used": 150},
    )
    agent_service.handle_event(event, msg, app_state)
    assert msg.mana_used == 150
    assert app_state.total_mana_used == 150


def test_handle_command_spell_dispatch(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify bash spell dispatch generates a Ran N Commands step card."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    # Start spell
    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={
            "spellCastId": "cast-1",
            "spellName": "bash",
            "command": "pytest -v",
        },
    )
    agent_service.handle_event(start_event, msg, app_state)

    cmd_steps = [s for s in msg.steps if s.step_type == StepType.COMMANDS]
    assert len(cmd_steps) == 1
    assert len(cmd_steps[0].commands) == 1
    assert "pytest -v" in cmd_steps[0].commands[0].command

    # End spell
    end_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_END,
        data={
            "spellCastId": "cast-1",
            "result": "82 passed in 0.45s",
        },
    )
    agent_service.handle_event(end_event, msg, app_state)
    assert cmd_steps[0].commands[0].output == "82 passed in 0.45s"
    assert cmd_steps[0].commands[0].is_error is False


def test_handle_file_exploration_spell_dispatch(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify read/grep spell dispatch generates an Explored N Files step card."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    # Read spell start
    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={
            "spellCastId": "cast-file-1",
            "spellName": "read",
            "path": "src/main.py",
            "lines": "1-50",
        },
    )
    agent_service.handle_event(start_event, msg, app_state)

    file_steps = [s for s in msg.steps if s.step_type == StepType.FILES]
    assert len(file_steps) == 1
    assert len(file_steps[0].files) == 1
    assert file_steps[0].files[0].path == "src/main.py"
    assert file_steps[0].files[0].lines == "1-50"

    # End spell
    end_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_END,
        data={
            "spellCastId": "cast-file-1",
            "result": "file contents...",
        },
    )
    agent_service.handle_event(end_event, msg, app_state)
    assert file_steps[0].files[0].details == "file contents..."


def test_handle_generic_worked_step(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify generic spell dispatch generates a Worked for Xs step card."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={
            "spellCastId": "cast-edit-1",
            "spellName": "edit",
            "path": "config.py",
        },
    )
    agent_service.handle_event(start_event, msg, app_state)

    worked_steps = [s for s in msg.steps if s.step_type == StepType.WORKED]
    assert len(worked_steps) == 1
    assert "edit" in worked_steps[0].details[0]

    end_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_END,
        data={
            "spellCastId": "cast-edit-1",
            "result": "Saved edits",
        },
    )
    agent_service.handle_event(end_event, msg, app_state)
    assert worked_steps[0].duration_seconds >= 0.0


def test_handle_agent_end_finalizes_state(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify AGENT_END marks message stream complete and is_channeling false."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)
    app_state.is_channeling = True

    event = MvgeEvent(type=MvgeEventType.AGENT_END, data={"stop_reason": "stop"})
    agent_service.handle_event(event, msg, app_state)

    assert msg.is_streaming is False
    assert app_state.is_channeling is False


def test_spell_casting_start_tracks_background_task(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify SPELL_CASTING_START registers a running background task in state."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={
            "spellCastId": "cast-bg-1",
            "spellName": "bash",
            "command": "pytest -v",
        },
    )
    agent_service.handle_event(start_event, msg, app_state)

    assert len(app_state.background_tasks) == 1
    task = app_state.background_tasks[0]
    assert task.id == "cast-bg-1"
    assert task.name == "bash"
    assert task.status == TaskStatus.RUNNING
    assert task.progress == 0.0


def test_spell_casting_start_is_idempotent_on_duplicate_id(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify duplicate spellCastId does not create a second background task."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={"spellCastId": "cast-bg-2", "spellName": "read"},
    )
    agent_service.handle_event(start_event, msg, app_state)
    agent_service.handle_event(start_event, msg, app_state)

    assert len(app_state.background_tasks) == 1


def test_spell_casting_start_uses_parent_spell_id(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify parentSpellCastId is propagated onto the background task."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={
            "spellCastId": "cast-child",
            "spellName": "edit",
            "parentSpellCastId": "cast-parent",
        },
    )
    agent_service.handle_event(start_event, msg, app_state)

    assert app_state.background_tasks[0].parent_id == "cast-parent"


def test_spell_casting_end_marks_task_complete(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify SPELL_CASTING_END finalises the background task as complete."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={"spellCastId": "cast-bg-3", "spellName": "bash"},
    )
    agent_service.handle_event(start_event, msg, app_state)

    end_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_END,
        data={
            "spellCastId": "cast-bg-3",
            "result": "82 passed in 0.45s",
        },
    )
    agent_service.handle_event(end_event, msg, app_state)

    task = app_state.background_tasks[0]
    assert task.status == TaskStatus.COMPLETE
    assert task.result == "82 passed in 0.45s"
    assert task.progress == 100.0
    assert task.ended_at is not None


def test_spell_casting_end_marks_task_error(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify SPELL_CASTING_END with an error marks the task errored."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={"spellCastId": "cast-bg-4", "spellName": "bash"},
    )
    agent_service.handle_event(start_event, msg, app_state)

    end_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_END,
        data={
            "spellCastId": "cast-bg-4",
            "error": "Command timed out",
        },
    )
    agent_service.handle_event(end_event, msg, app_state)

    task = app_state.background_tasks[0]
    assert task.status == TaskStatus.ERROR
    assert task.error == "Command timed out"
    assert task.progress == 100.0


def test_spell_casting_end_unknown_id_is_noop(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify SPELL_CASTING_END for an unknown spell id does not crash."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    end_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_END,
        data={"spellCastId": "never-started", "result": "ok"},
    )
    agent_service.handle_event(end_event, msg, app_state)

    assert app_state.background_tasks == []


def test_spell_casting_start_without_id_is_noop(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify a spell cast with no spellCastId does not create a task."""
    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    start_event = MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={"spellName": "bash"},
    )
    agent_service.handle_event(start_event, msg, app_state)

    assert app_state.background_tasks == []


def test_register_subagent_task(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify register_subagent_task adds a subagent background task."""
    task = agent_service.register_subagent_task(
        app_state, "sub-1", "Reviewer", parent_id="cast-parent"
    )
    assert task is not None
    assert task.id == "sub-1"
    assert task.name == "Reviewer"
    assert task.parent_id == "cast-parent"
    assert task.status == TaskStatus.RUNNING


def test_register_subagent_task_idempotent(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify register_subagent_task is idempotent on duplicate id."""
    agent_service.register_subagent_task(app_state, "sub-2", "First")
    task = agent_service.register_subagent_task(app_state, "sub-2", "Second")
    assert len(app_state.background_tasks) == 1
    assert task.name == "First"


def test_update_subagent_task_progress_and_status(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify update_subagent_task updates progress and status."""
    agent_service.register_subagent_task(app_state, "sub-3", "Worker")

    updated = agent_service.update_subagent_task(
        app_state, "sub-3", status=TaskStatus.COMPLETE, progress=100.0
    )
    assert updated is not None
    assert updated.status == TaskStatus.COMPLETE
    assert updated.progress == 100.0


def test_update_subagent_task_unknown_id_returns_none(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify update_subagent_task returns None for unknown task id."""
    assert (
        agent_service.update_subagent_task(app_state, "missing", progress=50.0)
        is None
    )


def test_background_tasks_cleared_on_new_conversation(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify new_conversation clears tracked background tasks."""
    agent_service.register_subagent_task(app_state, "sub-x", "Worker")
    app_state.new_conversation()
    assert app_state.background_tasks == []


def test_format_duration_variants() -> None:
    """Verify _format_duration correctly renders seconds and minutes."""
    assert AgentService._format_duration(0.4) == "0.4s"
    assert AgentService._format_duration(25.3) == "25.3s"
    assert AgentService._format_duration(125.0) == "2m 5s"


@pytest.mark.asyncio
async def test_run_prompt_no_api_key(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify run_prompt gives helpful instructions when no API key exists."""
    agent_service._api_key = None

    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    await agent_service.run_prompt("Hello", app_state, msg)
    assert msg.is_error is True
    assert "Authentication Required" in msg.content
    assert agent_service.is_running is False


@pytest.mark.asyncio
async def test_run_prompt_success(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify run_prompt drives agent.run successfully and switches model."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock()
    mock_agent.switch_model = AsyncMock()
    mock_agent.on = MagicMock()
    agent_service._agent = mock_agent

    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)
    app_state.selected_model = "anthropic/claude-3-5-sonnet"

    await agent_service.run_prompt("Build feature", app_state, msg)

    mock_agent.switch_model.assert_called_once_with("anthropic/claude-3-5-sonnet")
    mock_agent.run.assert_called_once_with("Build feature")
    assert agent_service.is_running is False


@pytest.mark.asyncio
async def test_run_prompt_cancelled_error(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify run_prompt handles asyncio.CancelledError."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=asyncio.CancelledError())
    mock_agent.switch_model = AsyncMock()
    mock_agent.on = MagicMock()
    agent_service._agent = mock_agent

    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    await agent_service.run_prompt("Test cancel", app_state, msg)
    assert "Cancelled by summoner" in msg.content
    assert agent_service.is_running is False


@pytest.mark.asyncio
async def test_run_prompt_authentication_error(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify run_prompt handles AuthenticationError with 401 message."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=AuthenticationError("HTTP 401"))
    mock_agent.switch_model = AsyncMock()
    mock_agent.on = MagicMock()
    agent_service._agent = mock_agent

    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    await agent_service.run_prompt("Test 401", app_state, msg)
    assert msg.is_error is True
    assert "Authentication Failed (HTTP 401)" in msg.content


@pytest.mark.asyncio
async def test_run_prompt_exception_handling(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify run_prompt handles general exceptions."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=ValueError("Model rejected"))
    mock_agent.switch_model = AsyncMock()
    mock_agent.on = MagicMock()
    agent_service._agent = mock_agent

    msg = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg)

    await agent_service.run_prompt("Test error", app_state, msg)
    assert msg.is_error is True
    assert "Model rejected" in msg.content


def test_agent_service_cancel_method(agent_service: AgentService) -> None:
    """Verify cancel() cancels active task."""
    mock_task = MagicMock()
    agent_service._active_task = mock_task
    agent_service._is_running = True

    agent_service.cancel()
    mock_task.cancel.assert_called_once()
    assert agent_service.is_running is False


@pytest.mark.asyncio
async def test_multi_turn_prompt_isolation(
    agent_service: AgentService, app_state: AppState
) -> None:
    """Verify consecutive prompts only update their respective ChatMessage."""
    callbacks: dict[MvgeEventType, list[Any]] = {}

    def mock_on(event_type: MvgeEventType, cb: Any) -> None:
        callbacks.setdefault(event_type, []).append(cb)

    mock_agent = MagicMock()
    mock_agent.on = MagicMock(side_effect=mock_on)
    mock_agent.switch_model = AsyncMock()

    async def fake_run_turn_1(prompt: str) -> None:
        for cb in callbacks.get(MvgeEventType.MESSAGE_UPDATE, []):
            cb(
                MvgeEvent(
                    type=MvgeEventType.MESSAGE_UPDATE,
                    data={"text": "Turn 1 Thought", "kind": "contemplation"},
                )
            )
            cb(
                MvgeEvent(
                    type=MvgeEventType.MESSAGE_UPDATE,
                    data={"text": "Turn 1 Response"},
                )
            )
        for cb in callbacks.get(MvgeEventType.AGENT_END, []):
            cb(MvgeEvent(type=MvgeEventType.AGENT_END, data={}))

    async def fake_run_turn_2(prompt: str) -> None:
        for cb in callbacks.get(MvgeEventType.MESSAGE_UPDATE, []):
            cb(
                MvgeEvent(
                    type=MvgeEventType.MESSAGE_UPDATE,
                    data={"text": "Turn 2 Thought", "kind": "contemplation"},
                )
            )
            cb(
                MvgeEvent(
                    type=MvgeEventType.MESSAGE_UPDATE,
                    data={"text": "Turn 2 Response"},
                )
            )
        for cb in callbacks.get(MvgeEventType.AGENT_END, []):
            cb(MvgeEvent(type=MvgeEventType.AGENT_END, data={}))

    agent_service._agent = mock_agent

    # Turn 1
    mock_agent.run = AsyncMock(side_effect=fake_run_turn_1)
    msg1 = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg1)
    await agent_service.run_prompt("hey there", app_state, msg1)

    assert msg1.contemplation == "Turn 1 Thought"
    assert msg1.content == "Turn 1 Response"

    # Turn 2
    mock_agent.run = AsyncMock(side_effect=fake_run_turn_2)
    msg2 = ChatMessage(role="assistant", is_streaming=True)
    app_state.messages.append(msg2)
    await agent_service.run_prompt("read README.md", app_state, msg2)

    # Turn 1 must NOT be polluted by Turn 2
    assert msg1.contemplation == "Turn 1 Thought"
    assert msg1.content == "Turn 1 Response"

    # Turn 2 has its own distinct content
    assert msg2.contemplation == "Turn 2 Thought"
    assert msg2.content == "Turn 2 Response"
