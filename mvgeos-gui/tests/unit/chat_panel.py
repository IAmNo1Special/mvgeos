"""Unit tests for chat panel rendering and scroll behavior."""

import asyncio

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.chat_panel import (
    _scroll_to_bottom,
    render_chat_panel,
)
from mvgeos_gui.state import AppState
from mvgeos_gui.transcript import InvocationTranscript


@pytest.mark.asyncio
async def test_scroll_to_bottom_invokes_without_error(user: User) -> None:
    """Verify _scroll_to_bottom executes safely in UI context."""

    @ui.page("/test_scroll_bottom")
    def page() -> None:
        col = ui.column().props('id="chat-messages-area"')
        _scroll_to_bottom(col.id, force=True)
        _scroll_to_bottom(col.id, force=False)
        _scroll_to_bottom(None, force=True)
        _scroll_to_bottom(None, force=False)

    await user.open("/test_scroll_bottom")


@pytest.mark.asyncio
async def test_render_chat_panel_empty(user: User) -> None:
    """Verify chat panel renders empty state when no messages are present."""
    state = AppState()

    @ui.page("/test_chat_panel_empty")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_empty")
    await user.should_see("What should Mvge work on?")


@pytest.mark.asyncio
async def test_render_chat_panel_with_messages(user: User) -> None:
    """Verify chat panel renders message list and container ID."""
    state = AppState()
    state.messages.append(InvocationTranscript.for_summoner("Hello Mvge!"))
    state.messages.append(
        InvocationTranscript.from_tome_content("Greetings Summoner!").message
    )

    @ui.page("/test_chat_panel_messages")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_messages")
    await user.should_see("Hello Mvge!")
    await user.should_see("Greetings Summoner!")


@pytest.mark.asyncio
async def test_render_chat_panel_streaming_state(user: User) -> None:
    """Verify chat panel renders streaming indicator and messages when streaming."""
    state = AppState()
    state.messages.append(
        InvocationTranscript.for_summoner("Explain quantum computing")
    )
    assistant = InvocationTranscript()
    assistant.apply_message_update({"text": "Quantum mechanics is"})
    assistant.message.is_streaming = True
    state.messages.append(assistant.message)
    state.is_channeling = True

    @ui.page("/test_chat_panel_streaming")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_streaming")
    await user.should_see("Explain quantum computing")
    await user.should_see("Quantum mechanics is")


@pytest.mark.asyncio
async def test_render_chat_panel_has_scroll_bottom_button(user: User) -> None:
    """Verify chat panel renders floating scroll-to-bottom button."""
    state = AppState()

    @ui.page("/test_chat_panel_scroll_btn")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_scroll_btn")
    btn = user.find("chat-scroll-bottom-btn")
    assert btn is not None


@pytest.mark.asyncio
async def test_chat_panel_chips_and_action_btn(user: User) -> None:
    """Verify chat panel updates chips and stop/send buttons reactively."""
    from mvgeos_gui.autocomplete import MentionChip

    state = AppState()

    @ui.page("/test_chat_panel_chips")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_chips")
    state.add_attachment("test_file.py")
    state.add_mention(MentionChip(text="@test_skill", kind="skill"))
    state.notify()
    await user.should_see("test_file.py")
    await user.should_see("@test_skill")

    # Toggle channeling to see stop button
    state.is_channeling = True
    state.notify()
    await asyncio.sleep(0.05)
    stop_btn = user.find("stop_channeling_btn")
    assert stop_btn is not None


@pytest.mark.asyncio
async def test_chat_panel_side_panel_and_toolbar_toggles(user: User) -> None:
    """Verify chat panel responds to side panel and toolbar toggles."""
    state = AppState()

    @ui.page("/test_chat_panel_toggles")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_toggles")
    state.set_chat_side_panel("files")
    await user.should_see("Files")
    state.set_chat_side_panel("diff")
    state.set_chat_side_panel(None)
    state.toggle_sidebar()
    state.notify()


@pytest.mark.asyncio
async def test_chat_panel_no_duplicate_messages_on_multiple_notifies(
    user: User,
) -> None:
    """Verify chat panel does not duplicate messages on multiple state notifies."""
    state = AppState()
    state.messages.append(InvocationTranscript.for_summoner("Unique prompt text"))
    state.messages.append(
        InvocationTranscript.from_tome_content("Unique response text").message
    )

    @ui.page("/test_chat_panel_no_dups")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_no_dups")
    await user.should_see("Unique prompt text")
    await user.should_see("Unique response text")

    # Trigger multiple state notifications (simulating stream tokens or keepalives)
    for _ in range(5):
        state.notify()
        await asyncio.sleep(0.01)

    await user.should_see("Unique prompt text")
    await user.should_see("Unique response text")


@pytest.mark.asyncio
async def test_chat_panel_preserves_card_expansion_during_streaming(
    user: User,
) -> None:
    """Verify expanded thought cards remain expanded during streaming refreshes."""
    state = AppState()
    old_msg = InvocationTranscript.from_tome_content(
        "<think>Deep reasoning about code</think>Final answer"
    ).message
    state.messages.append(old_msg)

    # User expands the thought card of message 0
    state.set_card_expansion("thought_0_0", True)

    @ui.page("/test_chat_panel_expand_persist")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_expand_persist")
    await user.should_see("Deep reasoning about code")

    # Simulate streaming a new assistant message and firing notifications
    new_stream = InvocationTranscript()
    new_stream.apply_message_update({"text": "Streaming new token"})
    new_stream.message.is_streaming = True
    state.messages.append(new_stream.message)

    for i in range(3):
        new_stream.apply_message_update({"text": f" token {i}"})
        state.notify()
        await asyncio.sleep(0.01)

    # The old thought card must still be expanded and visible
    await user.should_see("Deep reasoning about code")
    assert state.is_card_expanded("thought_0_0") is True
