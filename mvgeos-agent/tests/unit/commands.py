from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_provider.model_registry import ModelRegistry
from mvgeos_provider.types import Model

from mvgeos_agent.commands import (
    SLASH_COMMANDS,
    CommandAction,
    CommandDispatcher,
)
from mvgeos_agent.protocol import MvgeAgent
from mvgeos_agent.types import QueueMode


def _create_mock_agent(
    tome_id: str = "tome-123",
    model_id: str = "nvidia/nemotron-3-ultra-550b-a55b:free",
    queue_mode: QueueMode = QueueMode.ONE_AT_A_TIME,
    enabled_spells: list[str] | None = None,
    available_spells: list[str] | None = None,
    registered_providers: list[str] | None = None,
) -> MagicMock:
    agent = MagicMock(spec=MvgeAgent)
    agent.tome_id = tome_id
    agent.model_id = model_id
    agent.queue_mode = queue_mode
    agent.enabled_spells = (
        enabled_spells if enabled_spells is not None else ["read", "write"]
    )
    agent.available_spells = (
        available_spells
        if available_spells is not None
        else ["read", "write", "bash", "edit"]
    )
    agent.registered_providers = (
        registered_providers if registered_providers is not None else ["openrouter"]
    )
    agent.switch_model = AsyncMock()
    agent.set_enabled_spells = MagicMock()
    agent.steer = MagicMock()
    agent.follow_up = MagicMock()
    agent.reset_session = AsyncMock()
    return agent


def _create_mock_registry(models: list[Model] | None = None) -> MagicMock:
    reg = MagicMock(spec=ModelRegistry)
    m1 = Model(
        id="google/gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-test",
        is_free=True,
    )
    m2 = Model(
        id="anthropic/claude-3.5-sonnet",
        name="Claude 3.5 Sonnet",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-test",
        is_free=False,
    )
    model_list = models if models is not None else [m1, m2]
    reg.list_all.return_value = model_list
    reg.get.side_effect = lambda mid: next((m for m in model_list if m.id == mid), None)
    reg.refresh = AsyncMock(return_value=5)
    return reg


@pytest.mark.asyncio
async def test_slash_commands_catalog() -> None:
    assert "/help" in SLASH_COMMANDS
    assert "/quit" in SLASH_COMMANDS
    assert "/model" in SLASH_COMMANDS
    assert "/spells" in SLASH_COMMANDS


@pytest.mark.asyncio
async def test_help_command() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/help")
    assert outcome.action == CommandAction.HELP
    assert outcome.command == "/help"
    assert not outcome.should_exit
    assert outcome.data["commands"] == SLASH_COMMANDS
    assert "Available commands" in outcome.message


@pytest.mark.asyncio
async def test_quit_and_exit_commands() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)

    outcome_quit = await dispatcher.dispatch("/quit")
    assert outcome_quit.action == CommandAction.EXIT
    assert outcome_quit.should_exit is True

    outcome_exit = await dispatcher.dispatch("/exit")
    assert outcome_exit.action == CommandAction.EXIT
    assert outcome_exit.should_exit is True


@pytest.mark.asyncio
async def test_tome_command() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/tome")
    assert outcome.action == CommandAction.TOME_INFO
    assert outcome.data["tome_id"] == "tome-123"
    assert outcome.data["model_id"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert outcome.data["enabled_spells"] == ["read", "write"]
    assert "tome-123" in outcome.message


@pytest.mark.asyncio
async def test_models_list_all() -> None:
    agent = _create_mock_agent()
    reg = _create_mock_registry()
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/models")
    assert outcome.action == CommandAction.MODELS_LISTED
    assert len(outcome.data["models"]) == 2
    assert "google/gemini-2.5-flash" in outcome.message


@pytest.mark.asyncio
async def test_models_list_free_only() -> None:
    agent = _create_mock_agent()
    reg = _create_mock_registry()
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/models --free")
    assert outcome.action == CommandAction.MODELS_LISTED
    assert len(outcome.data["models"]) == 1
    assert outcome.data["models"][0].id == "google/gemini-2.5-flash"


@pytest.mark.asyncio
async def test_model_switch_success() -> None:
    agent = _create_mock_agent()
    reg = _create_mock_registry()
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/model google/gemini-2.5-flash")
    assert outcome.action == CommandAction.MODEL_SWITCHED
    assert outcome.data["model_id"] == "google/gemini-2.5-flash"
    agent.switch_model.assert_awaited_once_with("google/gemini-2.5-flash")
    assert "Model switched: google/gemini-2.5-flash" in outcome.message


@pytest.mark.asyncio
async def test_model_switch_unknown_model() -> None:
    agent = _create_mock_agent()
    reg = _create_mock_registry()
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/model non-existent-model")
    assert outcome.action == CommandAction.ERROR
    assert "Unknown model" in outcome.message
    agent.switch_model.assert_not_called()


@pytest.mark.asyncio
async def test_model_switch_failure() -> None:
    agent = _create_mock_agent()
    agent.switch_model.side_effect = RuntimeError("Switch failed")
    reg = _create_mock_registry()
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/model google/gemini-2.5-flash")
    assert outcome.action == CommandAction.ERROR
    assert "Switch failed" in outcome.message


@pytest.mark.asyncio
async def test_refresh_models_success() -> None:
    agent = _create_mock_agent()
    reg = _create_mock_registry()
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/refresh-models")
    assert outcome.action == CommandAction.CATALOG_REFRESHED
    assert outcome.data["new_models_count"] == 5
    reg.refresh.assert_awaited_once_with(force_refresh=True)


@pytest.mark.asyncio
async def test_refresh_models_failure() -> None:
    agent = _create_mock_agent()
    reg = _create_mock_registry()
    reg.refresh.side_effect = ConnectionError("Network down")
    dispatcher = CommandDispatcher(agent, registry=reg)
    outcome = await dispatcher.dispatch("/refresh-models")
    assert outcome.action == CommandAction.ERROR
    assert "Failed to refresh models: Network down" in outcome.message


@pytest.mark.asyncio
async def test_spells_list() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/spells")
    assert outcome.action == CommandAction.SPELLS_LISTED
    assert outcome.data["enabled_spells"] == ["read", "write"]
    assert outcome.data["available_spells"] == ["read", "write", "bash", "edit"]
    assert "read, write" in outcome.message


@pytest.mark.asyncio
async def test_spells_update() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/spells bash, grep")
    assert outcome.action == CommandAction.SPELLS_UPDATED
    assert outcome.data["enabled_spells"] == ["bash", "grep"]
    agent.set_enabled_spells.assert_called_once_with(["bash", "grep"])
    assert "Spells set to: bash, grep" in outcome.message


@pytest.mark.asyncio
async def test_mode_toggle() -> None:
    agent = _create_mock_agent(queue_mode=QueueMode.ONE_AT_A_TIME)
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/mode")
    assert outcome.action == CommandAction.QUEUE_MODE_CHANGED
    assert outcome.data["queue_mode"] == QueueMode.ALL
    assert agent.queue_mode == QueueMode.ALL

    # Toggle back
    outcome2 = await dispatcher.dispatch("/mode")
    assert outcome2.action == CommandAction.QUEUE_MODE_CHANGED
    assert outcome2.data["queue_mode"] == QueueMode.ONE_AT_A_TIME
    assert agent.queue_mode == QueueMode.ONE_AT_A_TIME


@pytest.mark.asyncio
async def test_steer_with_and_without_args() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)

    outcome = await dispatcher.dispatch("/steer focus on tests")
    assert outcome.action == CommandAction.STEERING_QUEUED
    assert outcome.data["message"] == "focus on tests"
    agent.steer.assert_called_once_with("focus on tests")

    outcome_empty = await dispatcher.dispatch("/steer")
    assert outcome_empty.action == CommandAction.ERROR


@pytest.mark.asyncio
async def test_followup_with_and_without_args() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)

    outcome = await dispatcher.dispatch("/followup clean up later")
    assert outcome.action == CommandAction.FOLLOWUP_QUEUED
    assert outcome.data["message"] == "clean up later"
    agent.follow_up.assert_called_once_with("clean up later")

    outcome_empty = await dispatcher.dispatch("/followup")
    assert outcome_empty.action == CommandAction.INFO


@pytest.mark.asyncio
async def test_new_session_success() -> None:
    agent = _create_mock_agent(tome_id="new-tome-456")
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/new")
    assert outcome.action == CommandAction.SESSION_RESET
    assert outcome.data["tome_id"] == "new-tome-456"
    agent.reset_session.assert_awaited_once_with(resume_tome_id=None)


@pytest.mark.asyncio
async def test_new_session_failure() -> None:
    agent = _create_mock_agent()
    agent.reset_session.side_effect = RuntimeError("Reset failed")
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/new")
    assert outcome.action == CommandAction.ERROR
    assert "Reset failed" in outcome.message


@pytest.mark.asyncio
async def test_resume_session_success() -> None:
    agent = _create_mock_agent(tome_id="resumed-tome-789")
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/resume path/to/tome.jsonl")
    assert outcome.action == CommandAction.SESSION_RESUMED
    assert outcome.data["tome_id"] == "resumed-tome-789"
    assert outcome.data["path"] == "path/to/tome.jsonl"
    agent.reset_session.assert_awaited_once_with(resume_tome_id="path/to/tome.jsonl")


@pytest.mark.asyncio
async def test_resume_session_missing_arg() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/resume")
    assert outcome.action == CommandAction.ERROR
    assert "Usage: /resume" in outcome.message


@pytest.mark.asyncio
async def test_unknown_command() -> None:
    agent = _create_mock_agent()
    dispatcher = CommandDispatcher(agent)
    outcome = await dispatcher.dispatch("/foobar")
    assert outcome.action == CommandAction.ERROR
    assert "Unknown command: /foobar" in outcome.message
