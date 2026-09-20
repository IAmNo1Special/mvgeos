"""Unit tests for chat panel rendering and scroll behavior."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

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
async def test_chat_panel_side_panel_and_toolbar_toggles(
    user: User, tmp_path: Path
) -> None:
    """Verify chat panel responds to side panel and toolbar toggles."""
    proj = tmp_path / "proj"
    proj.mkdir()
    state = AppState(project_path=proj)

    @ui.page("/test_chat_panel_toggles")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_toggles")
    state.set_chat_side_panel("files")
    await user.should_see("Files")
    state.set_chat_side_panel("diff")
    state.set_chat_side_panel(None)


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


@pytest.mark.asyncio
async def test_chat_panel_shows_files_side_panel(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.chat_side_panel = "files"

    @ui.page("/test_chat_files")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_files")
    await user.should_see("Files")


@pytest.mark.asyncio
async def test_chat_panel_composer_uses_curvy_style(user: User) -> None:
    """Verify composer renders curvy glow wrapper with send button."""
    state = AppState()

    @ui.page("/test_chat_panel_curvy")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_panel_curvy")
    assert user.find("composer-curvy") is not None
    assert user.find("composer-main") is not None
    assert user.find("prompt_input") is not None
    assert user.find("send_prompt_btn") is not None


@pytest.mark.asyncio
async def test_chat_panel_rerender_does_not_accumulate_listeners(
    user: User,
) -> None:
    """Verify re-rendering the chat panel keeps view listeners stable."""
    state = AppState()

    @ui.page("/test_chat_panel_rerender")
    def page() -> None:
        render_chat_panel(state)
        first = state.view_listener_count()
        assert first > 0
        render_chat_panel(state)
        assert state.view_listener_count() == first

    await user.open("/test_chat_panel_rerender")
    await user.should_see("What should Mvge work on?")


@pytest.mark.asyncio
async def test_chat_panel_shows_diff_side_panel(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.chat_side_panel = "diff"
    # mock diff view
    state.get_selected_diff_view = MagicMock(return_value=None)

    @ui.page("/test_chat_diff")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_diff")
    await user.should_see("Diff")


@pytest.mark.asyncio
async def test_chat_panel_cascading_selector(user: User) -> None:
    """Verify 4-tier cascading selector renders tiers dynamically."""
    state = AppState()

    @ui.page("/test_chat_cascading")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_cascading")
    assert user.find("realm_select") is not None
    assert user.find("provider_select") is not None
    assert user.find("model_select") is not None
    assert user.find("contemplation_select") is not None


@pytest.mark.asyncio
async def test_chat_panel_toolbar_settings_opens_modal(user: User) -> None:
    """Toolbar Settings button must open the app settings modal, not a view.

    Regression test: it used to call set_current_view("settings"), which
    shell.py has no branch for, so it fell through to the chat view.
    """
    state = AppState()
    state.open_app_settings = MagicMock()

    @ui.page("/test_chat_toolbar_settings")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_chat_toolbar_settings")
    settings_btn = user.find(marker="chat_toolbar_settings_btn")
    assert settings_btn is not None
    settings_btn.click()
    state.open_app_settings.assert_called_once()


@pytest.mark.asyncio
async def test_empty_chat_renders_single_centered_composer(user: User) -> None:
    """Empty state hosts the real composer exactly once, inside the hero."""
    state = AppState()
    state.messages = []

    @ui.page("/test_empty_centered_composer")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_empty_centered_composer")
    await user.should_see("What should Mvge work on?")
    # Entering the scope asserts exactly one composer exists; nesting it in
    # the empty-state scope asserts it is centered there, not duplicated.
    with user.scope(marker="empty-state"), user.scope(marker="composer-curvy"):
        user.find(marker="prompt_input")


@pytest.mark.asyncio
async def test_chat_with_messages_renders_single_bottom_composer(
    user: User,
) -> None:
    """With messages, exactly one composer exists and the hero is gone."""
    state = AppState()
    state.messages.append(InvocationTranscript.for_summoner("Hello Mvge!"))

    @ui.page("/test_messaged_single_composer")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_messaged_single_composer")
    await user.should_not_see("What should Mvge work on?")
    with user.scope(marker="composer-curvy"):
        user.find(marker="prompt_input")


@pytest.mark.asyncio
async def test_composer_moves_on_first_message_without_duplicating(
    user: User,
) -> None:
    """Empty -> message transition keeps exactly one functional composer."""
    state = AppState()
    state.messages = []

    @ui.page("/test_composer_transition")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_composer_transition")
    with user.scope(marker="empty-state"), user.scope(marker="composer-curvy"):
        user.find(marker="prompt_input")
    state.messages.append(InvocationTranscript.for_summoner("Hello Mvge!"))
    state.notify()
    await user.should_not_see("What should Mvge work on?")
    with user.scope(marker="composer-curvy"):
        user.find(marker="prompt_input")


@pytest.mark.asyncio
async def test_composer_draft_survives_new_conversation(user: User) -> None:
    """Unsent text is restored when the composer moves to the empty state."""
    state = AppState()
    state.messages.append(InvocationTranscript.for_summoner("Hello Mvge!"))

    @ui.page("/test_composer_draft")
    def page() -> None:
        render_chat_panel(state)

    await user.open("/test_composer_draft")
    with user.scope(marker="composer-curvy"):
        user.find(marker="prompt_input")
    # Simulate what handle_input_change does on every keystroke.
    state.composer_draft = "unsent draft"
    state.new_conversation()
    state.notify()
    await user.should_see("What should Mvge work on?")
    with user.scope(marker="empty-state"), user.scope(marker="composer-curvy"):
        restored = user.find(marker="prompt_input")
        assert restored.elements
        assert (next(iter(restored.elements)).value or "") == "unsent draft"
