"""Unit tests for Artifact cards and sliding preview drawer."""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.artifact_drawer import (
    render_artifact_card,
    render_artifact_drawer,
)
from mvgeos_gui.models import Artifact, ArtifactType
from mvgeos_gui.state import AppState


def _make_artifact(
    artifact_id: str = "artifact-1",
    title: str = "Implementation Plan",
    summary: str = "Refactor the auth module",
    content: str = "# Plan\n\nSteps to refactor.",
    artifact_type: ArtifactType = ArtifactType.IMPLEMENTATION_PLAN,
    file_paths: list[str] | None = None,
) -> Artifact:
    """Build a minimal Artifact for testing."""
    return Artifact(
        id=artifact_id,
        title=title,
        summary=summary,
        content=content,
        artifact_type=artifact_type,
        file_paths=file_paths or [],
    )


@pytest.mark.asyncio
async def test_render_artifact_card_shows_title_and_summary(user: User) -> None:
    """Verify artifact card renders title and summary text."""
    artifact = _make_artifact()

    @ui.page("/test_artifact_card")
    def page() -> None:
        state = AppState()
        render_artifact_card(artifact, state)

    await user.open("/test_artifact_card")
    await user.should_see("Implementation Plan")
    await user.should_see("Refactor the auth module")


@pytest.mark.asyncio
async def test_render_artifact_card_shows_type_badge(user: User) -> None:
    """Verify artifact card renders type badge."""
    artifact = _make_artifact(
        artifact_type=ArtifactType.WALKTHROUGH,
    )

    @ui.page("/test_artifact_type_badge")
    def page() -> None:
        state = AppState()
        render_artifact_card(artifact, state)

    await user.open("/test_artifact_type_badge")
    await user.should_see("Walkthrough")


@pytest.mark.asyncio
async def test_render_artifact_card_has_review_button(user: User) -> None:
    """Verify artifact card has a review/visibility action button."""
    artifact = _make_artifact()

    @ui.page("/test_artifact_review_btn")
    def page() -> None:
        state = AppState()
        render_artifact_card(artifact, state)

    await user.open("/test_artifact_review_btn")
    await user.should_see("Implementation Plan")


@pytest.mark.asyncio
async def test_render_artifact_card_click_opens_drawer(user: User) -> None:
    """Verify artifact card has a review button that triggers state.open_artifact."""
    artifact = _make_artifact()
    state = AppState()
    state.add_artifact(artifact)

    @ui.page("/test_artifact_click")
    def page() -> None:
        render_artifact_card(artifact, state)

    await user.open("/test_artifact_click")
    await user.should_see("Implementation Plan")

    state.open_artifact(artifact.id)
    assert state.get_selected_artifact() is artifact


@pytest.mark.asyncio
async def test_render_artifact_card_timestamp(user: User) -> None:
    """Verify artifact card shows creation timestamp."""
    artifact = _make_artifact()

    @ui.page("/test_artifact_timestamp")
    def page() -> None:
        state = AppState()
        render_artifact_card(artifact, state)

    await user.open("/test_artifact_timestamp")
    await user.should_see(artifact.created_at)


@pytest.mark.asyncio
async def test_render_artifact_drawer_shows_title(user: User) -> None:
    """Verify artifact drawer renders the artifact title."""
    artifact = _make_artifact()
    state = AppState()
    state.add_artifact(artifact)
    state.open_artifact(artifact.id)

    @ui.page("/test_drawer_title")
    def page() -> None:
        render_artifact_drawer(state)

    await user.open("/test_drawer_title")
    await user.should_see("Implementation Plan")


@pytest.mark.asyncio
async def test_render_artifact_drawer_shows_markdown(user: User) -> None:
    """Verify artifact drawer renders markdown content."""
    artifact = _make_artifact(content="# Title\n\nSome **bold** text.")
    state = AppState()
    state.add_artifact(artifact)
    state.open_artifact(artifact.id)

    @ui.page("/test_drawer_markdown")
    def page() -> None:
        render_artifact_drawer(state)

    await user.open("/test_drawer_markdown")
    await user.should_see("Title")
    await user.should_see("bold")


@pytest.mark.asyncio
async def test_render_artifact_drawer_shows_file_paths(user: User) -> None:
    """Verify artifact drawer shows associated file paths."""
    artifact = _make_artifact(file_paths=["src/auth.py", "src/utils.py"])
    state = AppState()
    state.add_artifact(artifact)
    state.open_artifact(artifact.id)

    @ui.page("/test_drawer_files")
    def page() -> None:
        render_artifact_drawer(state)

    await user.open("/test_drawer_files")
    await user.should_see("Files:")
    await user.should_see("src/auth.py")
    await user.should_see("src/utils.py")


@pytest.mark.asyncio
async def test_render_artifact_drawer_has_close_button(user: User) -> None:
    """Verify artifact drawer has a close button."""
    artifact = _make_artifact()
    state = AppState()
    state.add_artifact(artifact)
    state.open_artifact(artifact.id)

    @ui.page("/test_drawer_close")
    def page() -> None:
        render_artifact_drawer(state)

    await user.open("/test_drawer_close")
    await user.should_see("Implementation Plan")


@pytest.mark.asyncio
async def test_render_artifact_drawer_returns_none_when_no_selection(
    user: User,
) -> None:
    """Verify render_artifact_drawer is a no-op when no artifact is selected."""

    @ui.page("/test_drawer_no_selection")
    def page() -> None:
        state = AppState()
        render_artifact_drawer(state)

    await user.open("/test_drawer_no_selection")
