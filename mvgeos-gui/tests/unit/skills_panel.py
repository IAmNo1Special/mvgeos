"""Unit tests for the Skills Panel component."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.skills_panel import render_skills_panel
from mvgeos_gui.models import SkillInfo
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_skills_panel_empty(user: User) -> None:
    """Skills panel should show empty message when active_skills is empty."""
    state = AppState()
    state.active_skills = []

    @ui.page("/test_skills_empty")
    def page() -> None:
        render_skills_panel(state)

    await user.open("/test_skills_empty")
    await user.should_see("Skills")
    await user.should_see("No skills loaded")


@pytest.mark.asyncio
async def test_render_skills_panel_with_skills(user: User) -> None:
    """Skills panel should render skill names, descriptions, and badges."""
    state = AppState()
    state.active_skills = [
        SkillInfo(
            name="code_review",
            description="Reviews code standards",
            scope="project",
            invoked=True,
        ),
        SkillInfo(
            name="git_workflow",
            description="",
            scope="global",
            invoked=False,
        ),
    ]

    @ui.page("/test_skills_populated")
    def page() -> None:
        render_skills_panel(state)

    await user.open("/test_skills_populated")
    await user.should_see("code_review")
    await user.should_see("Reviews code standards")
    await user.should_see("Invoked")
    await user.should_see("git_workflow")
    await user.should_see("No description")
    await user.should_see("global")


@pytest.mark.asyncio
async def test_skills_panel_back_to_chat_button(user: User) -> None:
    """Clicking Back to Chat button should switch view to chat."""
    state = AppState()
    state.set_current_view = MagicMock()

    @ui.page("/test_skills_back_btn")
    def page() -> None:
        render_skills_panel(state)

    await user.open("/test_skills_back_btn")
    user.find("Back to Chat").click()
    state.set_current_view.assert_called_once_with("chat")


@pytest.mark.asyncio
async def test_skills_panel_remove_skill(user: User) -> None:
    """Each active skill card should have a remove button that removes it."""
    state = AppState()
    state.active_skills = [
        SkillInfo(
            name="code_review",
            description="Reviews code",
            scope="project",
            invoked=False,
        ),
    ]

    @ui.page("/test_skills_remove")
    def page() -> None:
        render_skills_panel(state)

    await user.open("/test_skills_remove")
    await user.should_see("code_review")
    user.find(marker="skill_remove_code_review").click()
    assert state.active_skills == []
    await user.should_see("No skills loaded")


@pytest.mark.asyncio
async def test_skills_panel_add_available_skill(user: User) -> None:
    """Discovered-but-inactive skills should show an Add button."""
    from mvgeos_runes.types import SkillManifest

    state = AppState()
    state.active_skills = []
    state.load_skills = MagicMock(  # type: ignore[method-assign]
        return_value=[
            SkillManifest(
                name="discovered-skill",
                description="A discovered skill",
                path="/home/user/.agents/skills/discovered-skill",
            ),
        ]
    )

    @ui.page("/test_skills_add")
    def page() -> None:
        render_skills_panel(state)

    await user.open("/test_skills_add")
    await user.should_see("discovered-skill")
    await user.should_see("Available Skills")
    user.find(marker="skill_add_discovered-skill").click()
    assert [s.name for s in state.active_skills] == ["discovered-skill"]


@pytest.mark.asyncio
async def test_skills_panel_install_dialog(user: User) -> None:
    """Install button should open a dialog to install from URL or path."""
    from unittest.mock import AsyncMock

    state = AppState()
    state.active_skills = []
    state.load_skills = MagicMock(return_value=[])  # type: ignore[method-assign]
    state.install_skill_async = AsyncMock(return_value="new-skill")  # type: ignore[method-assign]

    @ui.page("/test_skills_install")
    def page() -> None:
        render_skills_panel(state)

    await user.open("/test_skills_install")
    user.find(marker="skill_install_btn").click()
    await user.should_see("Install Skill")
    await user.should_see("Git URL or local path")
