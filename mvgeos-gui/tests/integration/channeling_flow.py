"""Integration tests for live agent channeling, Mana tracking, and step cards."""

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.app import build_page
from mvgeos_gui.models import (
    ChatMessage,
    CommandExecution,
    ExecutionStep,
    FileExploration,
    StepType,
)
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_user_and_assistant_message_rendering(user: User) -> None:
    """Verify user message bubble and assistant response bubble rendering."""
    state = AppState(project_path=Path("C:/demo/project"))
    state.messages.append(
        ChatMessage(role="user", content="Refactor the database module")
    )
    state.messages.append(
        ChatMessage(
            role="assistant",
            content="I have refactored the database connection pool.",
            model="nvidia/nemotron-3-ultra-550b-a55b:free",
            mana_used=1250,
        )
    )

    @ui.page("/test_messages_render")
    def page() -> None:
        build_page(state)

    await user.open("/test_messages_render")

    # User message
    await user.should_see("Summoner")
    await user.should_see("Refactor the database module")

    # Assistant message
    await user.should_see("Mvge")
    await user.should_see("nemotron-3-ultra")
    await user.should_see("1,250 Mana")
    await user.should_see("I have refactored the database connection pool.")


@pytest.mark.asyncio
async def test_collapsible_step_cards_in_conversation(user: User) -> None:
    """Verify intermediate step cards render in assistant response bubble."""
    state = AppState(project_path=Path("C:/demo/project"))
    assistant_msg = ChatMessage(
        role="assistant",
        content="Here are the search results.",
        steps=[
            ExecutionStep(
                step_type=StepType.WORKED,
                title="Worked for 3.1s",
                details=["Analyzed directory structure", "Parsed abstract syntax tree"],
                is_complete=True,
            ),
            ExecutionStep(
                step_type=StepType.FILES,
                title="Explored 2 files",
                files=[
                    FileExploration(
                        path="src/main.py", lines="L1-100", operation="read"
                    ),
                    FileExploration(
                        path="src/utils.py", lines="L50-75", operation="grep"
                    ),
                ],
            ),
            ExecutionStep(
                step_type=StepType.COMMANDS,
                title="Ran 1 command",
                commands=[
                    CommandExecution(
                        command="git status",
                        output="On branch main\nnothing to commit",
                        duration_seconds=0.15,
                    )
                ],
            ),
        ],
    )
    state.messages.append(assistant_msg)

    @ui.page("/test_step_cards_flow")
    def page() -> None:
        build_page(state)

    await user.open("/test_step_cards_flow")

    await user.should_see("Worked for 3.1s")
    await user.should_see("Explored 2 files")
    await user.should_see("Ran 1 command")
    await user.should_see("src/main.py")
    await user.should_see("git status")


@pytest.mark.asyncio
async def test_streaming_indicator_and_stop_button(user: User) -> None:
    """Verify channeling indicator and Stop button during active generation."""
    state = AppState(project_path=Path("C:/demo/project"), is_channeling=True)
    state.messages.append(
        ChatMessage(
            role="assistant",
            content="Drafting response...",
            is_streaming=True,
        )
    )

    @ui.page("/test_channeling_flow")
    def page() -> None:
        build_page(state)

    await user.open("/test_channeling_flow")

    await user.should_see("Channeling response...")

    # Click stop button
    user.find("stop_channeling_btn").click()
    assert state.is_channeling is False


@pytest.mark.asyncio
async def test_feedback_buttons_interaction(user: User) -> None:
    """Verify thumbs up and thumbs down feedback toggle on assistant message."""
    state = AppState(project_path=Path("C:/demo/project"))
    state.messages.append(
        ChatMessage(
            role="assistant",
            content="All unit tests passed successfully.",
            model="google/gemini-2.5-pro",
        )
    )

    @ui.page("/test_feedback_flow")
    def page() -> None:
        build_page(state)

    await user.open("/test_feedback_flow")

    # Set thumbs up
    state.set_message_feedback(0, "up")
    assert state.messages[0].feedback == "up"

    # Toggle thumbs down
    state.set_message_feedback(0, "down")
    assert state.messages[0].feedback == "down"


@pytest.mark.asyncio
async def test_model_selector_dropdown(user: User) -> None:
    """Verify switching models via state."""
    state = AppState(project_path=Path("C:/demo/project"))

    @ui.page("/test_model_selector")
    def page() -> None:
        build_page(state)

    await user.open("/test_model_selector")

    state.switch_model("google/gemini-2.5-pro")
    assert state.selected_model == "google/gemini-2.5-pro"


@pytest.mark.asyncio
async def test_contemplation_card_in_conversation(user: User) -> None:
    """Verify contemplation/thought block renders separately from response content."""
    state = AppState(project_path=Path("C:/demo/project"))
    state.messages.append(
        ChatMessage(
            role="assistant",
            contemplation="User wants greeting. Respond politely.",
            content="Hey there! How can I help you today?",
            model="nvidia/nemotron-3-ultra-550b-a55b:free",
        )
    )

    @ui.page("/test_thought_rendering")
    def page() -> None:
        build_page(state)

    await user.open("/test_thought_rendering")
    await user.should_see("Thought")
    await user.should_see("User wants greeting. Respond politely.")
    await user.should_see("Hey there! How can I help you today?")
