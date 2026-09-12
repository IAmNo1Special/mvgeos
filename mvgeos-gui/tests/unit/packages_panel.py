"""Unit tests for the Packages Panel component."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.packages_panel import render_packages_panel
from mvgeos_gui.state import AppState


@pytest.mark.asyncio
async def test_render_packages_panel(user: User) -> None:
    """Packages panel should render title and empty installed message."""
    state = AppState()

    @ui.page("/test_packages_panel")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_panel")
    await user.should_see("Packages")
    await user.should_see("Installed")
    await user.should_see("No packages installed")


@pytest.mark.asyncio
async def test_packages_panel_back_to_chat_button(user: User) -> None:
    """Clicking Back to Chat button should switch view to chat."""
    state = AppState()
    state.set_current_view = MagicMock()

    @ui.page("/test_packages_back_btn")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_back_btn")
    user.find("Back to Chat").click()
    state.set_current_view.assert_called_once_with("chat")


@pytest.mark.asyncio
async def test_packages_panel_marketplace_listing_and_search(user: User) -> None:
    """Marketplace runes should be listed and filterable via search."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "alpha-rune": {
                "name": "alpha-rune",
                "version": "1.2.0",
                "runtime": "python",
                "description": "Alpha extension description",
                "git": "https://github.com/example/alpha",
            },
            "beta-rune": {
                "name": "beta-rune",
                "version": "2.0.0",
                "runtime": "python",
                "description": "Beta extension description",
                "git": "https://github.com/example/beta",
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[]
    )

    @ui.page("/test_packages_marketplace")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_marketplace")
    await user.should_see("alpha-rune")
    await user.should_see("beta-rune")
    await user.should_see("Alpha extension description")
    await user.should_see("Beta extension description")

    search_el = next(iter(user.find(marker="package_search_input").elements))
    search_el.value = "alpha"
    await user.should_see("alpha-rune")


@pytest.mark.asyncio
async def test_packages_panel_installed_items_and_uninstall(user: User) -> None:
    """Installed tab should render runes and allow uninstalling them."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "my-tool",
                "version": "1.0.0",
                "path": "/home/user/.agents/extensions/my-tool",
                "description": "Installed tool description",
            }
        ]
    )
    state.uninstall_rune_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_packages_installed")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_installed")
    # Switch to installed tab
    user.find(marker="package_tab_installed").click()
    await user.should_see("my-tool")
    await user.should_see("/home/user/.agents/extensions/my-tool")
    await user.should_see("Installed tool description")

    # Click uninstall
    user.find(marker="package_uninstall_item_my-tool").click()
    await user.should_see("Uninstalling my-tool...")
    state.uninstall_rune_async.assert_called_once_with("my-tool")

    # Test failure branch of uninstall
    state.uninstall_rune_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    user.find(marker="package_uninstall_item_my-tool").click()
    await user.should_see("Failed to uninstall my-tool")


@pytest.mark.asyncio
async def test_packages_panel_marketplace_install_flow(user: User) -> None:
    """Marketplace install button installs rune and shows installed badge."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "installed-rune": {
                "name": "installed-rune",
                "version": "1.0.0",
                "description": "Already installed rune",
                "git": "https://github.com/example/installed",
            },
            "uninstalled-rune": {
                "name": "uninstalled-rune",
                "version": "1.0.0",
                "description": "Not yet installed rune",
                "git": "https://github.com/example/uninstalled",
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.is_rune_installed = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda name: name == "installed-rune"
    )
    state.install_rune_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_packages_install_flow")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_install_flow")
    await user.should_see("Installed")
    await user.should_see("uninstalled-rune")

    # Click install on uninstalled-rune
    user.find(marker="package_install_item_uninstalled-rune").click()
    await user.should_see("Installing uninstalled-rune...")
    state.install_rune_async.assert_called_once_with("uninstalled-rune")

    # Test failure branch of install item
    state.install_rune_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    user.find(marker="package_install_item_uninstalled-rune").click()
    await user.should_see("Failed to install uninstalled-rune")


@pytest.mark.asyncio
async def test_packages_panel_install_dialog(user: User) -> None:
    """Install dialog should validate input and invoke install_rune_async."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.install_rune_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_packages_dialog")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_dialog")
    # Open dialog
    user.find(marker="package_open_install_dialog_btn").click()

    # Click install with empty input (should warn and return)
    user.find(marker="package_dialog_install_btn").click()
    await user.should_see("Please enter a rune source")
    state.install_rune_async.assert_not_called()

    # Enter source and install
    source_el = next(iter(user.find(marker="package_dialog_source_input").elements))
    source_el.set_value("https://github.com/example/custom-rune.git")
    user.find(marker="package_dialog_install_btn").click()
    await user.should_see("Installing https://github.com/example/custom-rune.git...")
    state.install_rune_async.assert_called_once_with(
        "https://github.com/example/custom-rune.git"
    )

    # Test dialog failure branch
    state.install_rune_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    source_el.set_value("failing-rune")
    user.find(marker="package_dialog_install_btn").click()
    await user.should_see("Failed to install failing-rune")

    # Test cancel button
    user.find(marker="package_dialog_cancel_btn").click()


@pytest.mark.asyncio
async def test_packages_panel_refresh_data_exceptions(user: User) -> None:
    """Panel should handle exceptions when fetching or listing runes."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("market error")
    )
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("installed error")
    )

    @ui.page("/test_packages_exceptions")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_exceptions")
    await user.should_see("Packages")
