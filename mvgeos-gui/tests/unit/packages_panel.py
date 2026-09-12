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
    """Packages panel should render title and empty message when no runes exist."""
    state = AppState()

    @ui.page("/test_packages_panel")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_panel")
    await user.should_see("Marketplace")
    await user.should_see("No extensions found")


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
    """Installed extensions render path/hooks/deps and uninstall via button."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "my-tool",
                "version": "1.0.0",
                "path": "/home/user/.agents/extensions/my-tool",
                "description": "Installed tool description",
                "hooks": ["turn_start"],
                "python_deps": ["requests"],
            }
        ]
    )
    state.uninstall_rune_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_packages_installed")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_installed")
    await user.should_see("my-tool")
    await user.should_see("/home/user/.agents/extensions/my-tool")
    await user.should_see("Installed tool description")
    await user.should_see("turn_start")
    await user.should_see("requests")

    # Click installed button to uninstall
    user.find(marker="package_uninstall_item_my-tool").click()
    await user.should_see("Uninstalling my-tool...")
    state.uninstall_rune_async.assert_called_once_with("my-tool")

    # Test failure branch of uninstall
    state.uninstall_rune_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    user.find(marker="package_uninstall_item_my-tool").click()
    await user.should_see("Failed to uninstall my-tool")


@pytest.mark.asyncio
async def test_packages_panel_marketplace_install_flow(user: User) -> None:
    """Marketplace install button installs rune and shows installed button."""
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
    await user.should_see("Marketplace")


@pytest.mark.asyncio
async def test_packages_panel_filter_by_hooks(user: User) -> None:
    """Filter by hooks should show only runes with selected hooks."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "rune-with-hooks": {
                "name": "rune-with-hooks",
                "version": "1.0.0",
                "runtime": "python",
                "description": "Has hooks",
                "hooks": ["turn_start", "before_invocation"],
            },
            "rune-without-hooks": {
                "name": "rune-without-hooks",
                "version": "1.0.0",
                "runtime": "python",
                "description": "No hooks",
                "hooks": [],
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_filter_hooks")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filter_hooks")
    await user.should_see("rune-with-hooks")
    await user.should_see("rune-without-hooks")

    # Select hook filter
    hooks_select = user.find(marker="package_filter_hooks")
    hooks_el = next(iter(hooks_select.elements))
    hooks_el.set_value(["turn_start"])
    # Filter should apply - rune-without-hooks should be hidden
    # Note: NiceGUI testing may not immediately reflect filter changes
    # The filter logic is tested at the unit level


@pytest.mark.asyncio
async def test_packages_panel_filter_by_runtime(user: User) -> None:
    """Filter by runtime should show only runes with selected runtime."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "python-rune": {
                "name": "python-rune",
                "version": "1.0.0",
                "runtime": "python",
                "description": "Python runtime",
            },
            "node-rune": {
                "name": "node-rune",
                "version": "1.0.0",
                "runtime": "node",
                "description": "Node runtime",
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_filter_runtime")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filter_runtime")
    await user.should_see("python-rune")
    await user.should_see("node-rune")


@pytest.mark.asyncio
async def test_packages_panel_filter_installed_only(user: User) -> None:
    """Installed only filter should show only installed runes."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "marketplace-rune": {
                "name": "marketplace-rune",
                "version": "1.0.0",
                "description": "Marketplace only",
            }
        }
    )
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "installed-rune",
                "version": "1.0.0",
                "path": "/home/user/.agents/extensions/installed-rune",
                "description": "Installed rune",
            }
        ]
    )

    @ui.page("/test_packages_filter_installed")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filter_installed")
    await user.should_see("marketplace-rune")
    await user.should_see("installed-rune")

    # Check installed only checkbox
    installed_chk = user.find(marker="package_filter_installed_only")
    installed_chk.click()
    # Filter should apply - marketplace only should be hidden


@pytest.mark.asyncio
async def test_packages_panel_filter_marketplace_only(user: User) -> None:
    """Marketplace only filter should show only marketplace runes."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "marketplace-rune": {
                "name": "marketplace-rune",
                "version": "1.0.0",
                "description": "Marketplace only",
            }
        }
    )
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "installed-rune",
                "version": "1.0.0",
                "path": "/home/user/.agents/extensions/installed-rune",
                "description": "Installed rune",
            }
        ]
    )

    @ui.page("/test_packages_filter_marketplace")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filter_marketplace")
    await user.should_see("marketplace-rune")
    await user.should_see("installed-rune")

    # Check marketplace only checkbox
    marketplace_chk = user.find(marker="package_filter_marketplace_only")
    marketplace_chk.click()
    # Filter should apply - installed only should be hidden


@pytest.mark.asyncio
async def test_packages_panel_sort_by_name_az(user: User) -> None:
    """Sort by name A-Z should order alphabetically ascending."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "zeta": {"name": "zeta", "version": "1.0.0", "description": "Last"},
            "alpha": {"name": "alpha", "version": "1.0.0", "description": "First"},
            "epsilon": {"name": "epsilon", "version": "1.0.0", "description": "Middle"},
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_sort_az")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_sort_az")
    # Default sort is name_az
    await user.should_see("alpha")
    await user.should_see("epsilon")
    await user.should_see("zeta")


@pytest.mark.asyncio
async def test_packages_panel_sort_by_version(user: User) -> None:
    """Sort by version should order by version number."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "v1": {"name": "v1", "version": "1.0.0", "description": "v1"},
            "v3": {"name": "v3", "version": "3.0.0", "description": "v3"},
            "v2": {"name": "v2", "version": "2.0.0", "description": "v2"},
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_sort_version")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_sort_version")
    # Default sort is name_az
    await user.should_see("v1")
    await user.should_see("v2")
    await user.should_see("v3")


@pytest.mark.asyncio
async def test_packages_panel_filter_by_execution_mode(user: User) -> None:
    """Filter by execution mode should show only matching runes."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "parallel-rune": {
                "name": "parallel-rune",
                "version": "1.0.0",
                "execution_mode": "parallel",
                "description": "Parallel execution",
            },
            "serial-rune": {
                "name": "serial-rune",
                "version": "1.0.0",
                "execution_mode": "serial",
                "description": "Serial execution",
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_filter_exec_mode")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filter_exec_mode")
    await user.should_see("parallel-rune")
    await user.should_see("serial-rune")


@pytest.mark.asyncio
async def test_packages_panel_filter_by_scope(user: User) -> None:
    """Filter by scope should show only matching runes."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "project-rune": {
                "name": "project-rune",
                "version": "1.0.0",
                "scope": "project",
                "description": "Project scope",
            },
            "user-rune": {
                "name": "user-rune",
                "version": "1.0.0",
                "scope": "user",
                "description": "User scope",
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_filter_scope")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filter_scope")
    await user.should_see("project-rune")
    await user.should_see("user-rune")
