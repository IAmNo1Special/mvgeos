import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.conversation_view import (
    render_assistant_message,
    render_conversation_view,
    render_user_message,
)
from mvgeos_gui.models import ChatMessage, MessagePart, MessagePartType
from mvgeos_gui.state import AppState


def _make_user_msg(content: str = "hello") -> ChatMessage:
    return ChatMessage(role="user", content=content)


def _make_assistant_msg(
    content: str = "response",
    is_streaming: bool = False,
    model: str = "openai/gpt-4",
    mana_used: int = 0,
) -> ChatMessage:
    msg = ChatMessage(
        role="assistant",
        content=content,
        is_streaming=is_streaming,
        model=model,
        mana_used=mana_used,
    )
    # ensure parts reflect content
    msg.parts = [MessagePart(part_type=MessagePartType.TEXT, text=content)]
    return msg


@pytest.mark.asyncio
async def test_render_user_message(user: User) -> None:
    msg = _make_user_msg("hello summoner")

    @ui.page("/test_user_msg")
    def page() -> None:
        render_user_message(msg)

    await user.open("/test_user_msg")
    await user.should_see("hello summoner")


@pytest.mark.asyncio
async def test_render_assistant_message_with_mana(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    msg = _make_assistant_msg("done", model="nvidia/nemotron:test", mana_used=1234)

    @ui.page("/test_assistant_mana")
    def page() -> None:
        render_assistant_message(msg, 0, state)

    await user.open("/test_assistant_mana")
    await user.should_see("done")


@pytest.mark.asyncio
async def test_render_assistant_streaming(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    msg = _make_assistant_msg("", is_streaming=True)
    msg.contemplation = ["thinking"]
    msg.parts = [MessagePart(part_type=MessagePartType.CONTEMPLATION, text="thinking")]

    @ui.page("/test_assistant_stream")
    def page() -> None:
        render_assistant_message(msg, 0, state)

    await user.open("/test_assistant_stream")
    await user.should_see("Contemplating")


@pytest.mark.asyncio
async def test_render_conversation_view_empty(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.active_tome_id = None

    @ui.page("/test_conv_empty")
    def page() -> None:
        render_conversation_view(state)

    await user.open("/test_conv_empty")
    await user.should_see("Active session")


@pytest.mark.asyncio
async def test_render_conversation_view_with_messages(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    state.messages.append(_make_user_msg("hi"))
    state.messages.append(_make_assistant_msg("hello"))

    @ui.page("/test_conv_msgs")
    def page() -> None:
        render_conversation_view(state)

    await user.open("/test_conv_msgs")
    await user.should_see("hi")
    await user.should_see("hello")
