import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.message_parts import (
    render_artifacts_section,
    render_contemplation_section,
    render_error_display,
    render_message_header,
    render_message_parts,
    render_streaming_indicator,
)
from mvgeos_gui.models import (
    Artifact,
    ArtifactType,
    ChatMessage,
    MessagePart,
    MessagePartType,
)
from mvgeos_gui.state import AppState


def _msg(**kwargs) -> ChatMessage:
    content = kwargs.pop("content", None)
    contemplation = kwargs.pop("contemplation", None)
    msg = ChatMessage(role="assistant", **kwargs)
    for thought in contemplation or []:
        msg.parts.append(
            MessagePart(part_type=MessagePartType.CONTEMPLATION, text=thought)
        )
    if content:
        msg.parts.append(MessagePart(part_type=MessagePartType.TEXT, text=content))
    return msg


@pytest.mark.asyncio
async def test_render_header_with_mana(user: User) -> None:
    msg = _msg(model="a/b:c", mana_used=100, content="hi")

    @ui.page("/test_msg_header")
    def page() -> None:
        render_message_header(msg)

    await user.open("/test_msg_header")
    await user.should_see("Mvge")


@pytest.mark.asyncio
async def test_render_parts_text_and_contemplation(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    msg = _msg(content="hello", contemplation=["think"])
    msg.parts = [
        MessagePart(part_type=MessagePartType.CONTEMPLATION, text="think"),
        MessagePart(part_type=MessagePartType.TEXT, text="hello"),
    ]

    @ui.page("/test_msg_parts")
    def page() -> None:
        render_message_parts(msg, state)

    await user.open("/test_msg_parts")
    await user.should_see("hello")


@pytest.mark.asyncio
async def test_render_contemplation_section(user: User) -> None:
    msg = _msg(contemplation=["a", "b"])

    @ui.page("/test_contemplation")
    def page() -> None:
        render_contemplation_section(msg)

    await user.open("/test_contemplation")


@pytest.mark.asyncio
async def test_render_streaming_indicator(user: User) -> None:
    msg = _msg(is_streaming=True, content="", contemplation=["x"])

    @ui.page("/test_streaming")
    def page() -> None:
        render_streaming_indicator(msg)

    await user.open("/test_streaming")
    await user.should_see("Contemplating")


@pytest.mark.asyncio
async def test_render_error_display(user: User) -> None:
    msg = _msg()
    msg.is_error = True
    msg.error_message = "boom"

    @ui.page("/test_error")
    def page() -> None:
        render_error_display(msg)

    await user.open("/test_error")
    await user.should_see("boom")


@pytest.mark.asyncio
async def test_render_artifacts_section(user: User, tmp_path) -> None:
    state = AppState(project_path=tmp_path)
    msg = _msg()
    msg.artifacts = [
        Artifact(id="1", title="T", content="c", artifact_type=ArtifactType.OTHER)
    ]

    @ui.page("/test_artifacts")
    def page() -> None:
        render_artifacts_section(msg, state)

    await user.open("/test_artifacts")
    await user.should_see("T")
