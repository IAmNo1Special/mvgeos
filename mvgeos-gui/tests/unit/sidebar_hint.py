"""Unit tests for the Sidebar Hint component."""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.sidebar_hint import sidebar_hint


@pytest.mark.asyncio
async def test_sidebar_hint_renders(user: User) -> None:
    """Sidebar hint should attach a tooltip with the given text."""

    @ui.page("/test_sidebar_hint")
    def page() -> None:
        with ui.button("Nav Item"):
            sidebar_hint("Dashboard")

    await user.open("/test_sidebar_hint")
    await user.should_see("Nav Item")
    await user.should_see("Dashboard")
