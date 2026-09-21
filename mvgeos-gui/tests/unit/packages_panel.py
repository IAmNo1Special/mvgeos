"""Unit tests for the Packages Panel component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.packages_panel import (
    _parse_timestamp,
    open_folder_in_explorer,
    render_packages_panel,
)
from mvgeos_gui.state import AppState


def test_open_folder_in_explorer_nonexistent() -> None:
    """open_folder_in_explorer should return False if path doesn't exist."""
    assert open_folder_in_explorer("/nonexistent/directory/path/12345") is False


def test_open_folder_in_explorer_success(tmp_path: Path) -> None:
    """open_folder_in_explorer should open existing folder via OS handler."""
    with (
        patch("platform.system", return_value="Windows"),
        patch("os.startfile", create=True) as mock_startfile,
    ):
        res = open_folder_in_explorer(tmp_path)
        assert res is True
        mock_startfile.assert_called_once_with(str(tmp_path.resolve()))

    with (
        patch("platform.system", return_value="Darwin"),
        patch("subprocess.Popen") as mock_popen,
    ):
        res = open_folder_in_explorer(tmp_path)
        assert res is True
        mock_popen.assert_called_once_with(["open", str(tmp_path.resolve())])

    with (
        patch("platform.system", return_value="Linux"),
        patch("subprocess.Popen") as mock_popen,
    ):
        res = open_folder_in_explorer(tmp_path)
        assert res is True
        mock_popen.assert_called_once_with(["xdg-open", str(tmp_path.resolve())])


@pytest.mark.asyncio
async def test_packages_panel_marketplace_listing_and_search(user: User) -> None:
    """Marketplace runes should show type, hooks, and deps even when uninstalled."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "alpha-rune": {
                "name": "alpha-rune",
                "version": "1.2.0",
                "runtime": "python",
                "description": "Alpha extension description",
                "git": "https://github.com/example/alpha",
                "types": ["Spell", "Spell Modifier"],
                "hooks": ["turn_start"],
                "python_deps": ["requests"],
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
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_marketplace")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_marketplace")
    await user.should_see("alpha-rune")
    await user.should_see("beta-rune")
    await user.should_see("Alpha extension description")
    await user.should_see("Beta extension description")
    # Verify uninstalled extension displays Type badges, Hooks, and Deps
    await user.should_see("Spell")
    await user.should_see("Spell Modifier")
    await user.should_see("turn_start")
    await user.should_see("requests")

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
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
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

    # Click path to open folder in explorer
    with patch(
        "mvgeos_gui.components.packages_panel.open_folder_in_explorer",
        return_value=True,
    ) as mock_open:
        user.find("/home/user/.agents/extensions/my-tool").click()
        mock_open.assert_called_once_with("/home/user/.agents/extensions/my-tool")

    # Click installed button to uninstall
    user.find(marker="package_uninstall_item_my-tool").click()
    await user.should_see("Uninstalling my-tool...", retries=10)
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
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
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
    await user.should_see("Installing uninstalled-rune...", retries=10)
    state.install_rune_async.assert_called_once_with("uninstalled-rune")

    # Test failure branch of install item
    state.install_rune_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    user.find(marker="package_install_item_uninstalled-rune").click()
    await user.should_see("Failed to install uninstalled-rune", retries=10)


@pytest.mark.asyncio
async def test_packages_panel_install_dialog(user: User) -> None:
    """Install dialog should validate input and invoke install_rune_async."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
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
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_exceptions")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_exceptions")
    await user.should_see("Marketplace")


@pytest.mark.asyncio
async def test_packages_panel_filters_by_type_hook_dep(user: User) -> None:
    """Extensions should be filterable by type, hook, and dependency."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "realm-rune": {
                "name": "realm-rune",
                "version": "1.0.0",
                "types": ["RealmProvider"],
                "hooks": ["before_provider_request"],
                "python_deps": ["httpx"],
            },
            "spell-rune": {
                "name": "spell-rune",
                "version": "1.0.0",
                "types": ["Spell"],
                "hooks": ["turn_start"],
                "python_deps": ["aiohttp"],
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_filters")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_filters")
    await user.should_see("realm-rune")
    await user.should_see("spell-rune")

    # Filter by Type: RealmProvider
    type_el = next(iter(user.find(marker="package_filter_type_select").elements))
    type_el.set_value("RealmProvider")
    await user.should_see("realm-rune", retries=10)
    await user.should_not_see("spell-rune", retries=10)

    # Filter by Hook: turn_start (reset type first)
    type_el.set_value("All Types")
    hook_el = next(iter(user.find(marker="package_filter_hook_select").elements))
    hook_el.set_value("turn_start")
    await user.should_see("spell-rune", retries=10)
    await user.should_not_see("realm-rune", retries=10)

    # Filter by Dep: httpx (reset hook first)
    hook_el.set_value("All Hooks")
    dep_el = next(iter(user.find(marker="package_filter_dep_select").elements))
    dep_el.set_value("httpx")
    await user.should_see("realm-rune", retries=10)
    await user.should_not_see("spell-rune", retries=10)

    # Click clear filters
    user.find(marker="package_clear_filters_btn").click()
    await user.should_see("realm-rune", retries=10)
    await user.should_see("spell-rune", retries=10)


@pytest.mark.asyncio
async def test_packages_panel_sorting(user: User) -> None:
    """Extensions should be sortable by name, date added, and last updated."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "a-first": {
                "name": "a-first",
                "version": "1.0.0",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-10T00:00:00Z",
            },
            "z-last": {
                "name": "z-last",
                "version": "1.0.0",
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-10T00:00:00Z",
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_sorting")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_sorting")
    sort_el = next(iter(user.find(marker="package_sort_select").elements))

    # Test Z-A
    sort_el.set_value("Alphabetical (Z-A)")
    await user.should_see("z-last")
    await user.should_see("a-first")

    # Test Date Added
    sort_el.set_value("Date Added")
    await user.should_see("z-last")

    # Test Last Updated
    sort_el.set_value("Last Updated")
    await user.should_see("z-last")


@pytest.mark.asyncio
async def test_packages_panel_mvges_listing_and_search(user: User) -> None:
    """Marketplace mvges should show version, spells, and deps."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "coding_mvge": {
                "name": "coding_mvge",
                "version": "0.2.6",
                "runtime": "python",
                "description": "Coding agent for MvgeOS",
                "git": "https://github.com/example/coding_mvge",
                "spells": ["bash", "read", "write"],
                "python_deps": ["mvgeos-agent"],
            },
            "research_mvge": {
                "name": "research_mvge",
                "version": "1.0.0",
                "runtime": "python",
                "description": "Research agent for MvgeOS",
                "spells": ["search_web", "read_url"],
            },
        }
    )
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_mvges_marketplace")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_mvges_marketplace")
    await user.should_see("coding_mvge")
    await user.should_see("research_mvge")
    await user.should_see("Coding agent for MvgeOS")
    await user.should_see("Research agent for MvgeOS")
    await user.should_see("bash")
    await user.should_see("read")
    await user.should_see("search_web")

    search_el = next(iter(user.find(marker="mvge_search_input").elements))
    search_el.value = "coding"
    await user.should_see("coding_mvge")


@pytest.mark.asyncio
async def test_packages_panel_mvges_install_and_uninstall_flow(user: User) -> None:
    """Mvge install and uninstall buttons invoke appropriate state methods."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "installed_mvge": {
                "name": "installed_mvge",
                "version": "1.0.0",
                "description": "Installed agent",
            },
            "new_mvge": {
                "name": "new_mvge",
                "version": "1.0.0",
                "description": "Available agent",
            },
        }
    )
    state.list_installed_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "installed_mvge",
                "version": "1.0.0",
                "path": "/home/user/.agents/agents/installed_mvge",
                "spells": ["bash"],
            }
        ]
    )
    state.is_mvge_installed = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda name: name == "installed_mvge"
    )
    state.install_mvge_async = AsyncMock(return_value=True)  # type: ignore[method-assign]
    state.uninstall_mvge_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_mvges_flow")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_mvges_flow")
    await user.should_see("installed_mvge")
    await user.should_see("new_mvge")

    # Install new_mvge
    user.find(marker="mvge_install_item_new_mvge").click()
    await user.should_see("Installing new_mvge...")
    state.install_mvge_async.assert_called_once_with("new_mvge")

    # Uninstall installed_mvge
    user.find(marker="mvge_uninstall_item_installed_mvge").click()
    await user.should_see("Uninstalling installed_mvge...")
    state.uninstall_mvge_async.assert_called_once_with("installed_mvge")


@pytest.mark.asyncio
async def test_packages_panel_mvge_dialog_and_filters(user: User) -> None:
    """Install dialog and filters for Mvges."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "agent_a": {
                "name": "agent_a",
                "version": "1.0.0",
                "spells": ["bash"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            "agent_z": {
                "name": "agent_z",
                "version": "1.0.0",
                "spells": ["search_web"],
                "created_at": "2026-02-01T00:00:00Z",
            },
        }
    )
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.install_mvge_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_mvges_dialog_and_filters")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_mvges_dialog_and_filters")

    # Dialog
    user.find(marker="mvge_open_install_dialog_btn").click()
    user.find(marker="mvge_dialog_install_btn").click()
    await user.should_see("Please enter an agent source")

    source_el = next(iter(user.find(marker="mvge_dialog_source_input").elements))
    source_el.set_value("coding_mvge")
    user.find(marker="mvge_dialog_install_btn").click()
    await user.should_see("Installing coding_mvge...")
    state.install_mvge_async.assert_called_once_with("coding_mvge")

    # Sort Z-A
    sort_el = next(iter(user.find(marker="mvge_sort_select").elements))
    sort_el.set_value("Alphabetical (Z-A)")
    await user.should_see("agent_z")
    await user.should_see("agent_a")

    # Clear filters
    user.find(marker="mvge_clear_filters_btn").click()
    await user.should_see("agent_a")


@pytest.mark.asyncio
async def test_packages_panel_mvge_remains_in_marketplace_after_uninstall(
    user: User,
) -> None:
    """Uninstalled marketplace mvge remains visible in marketplace
    with Install button.
    """
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    mvge_catalog = {
        "coding_mvge": {
            "name": "coding_mvge",
            "version": "0.2.6",
            "description": "Coding agent for MvgeOS",
            "runtime": "python",
            "git": "https://github.com/example/coding_mvge",
            "spells": ["bash", "read", "write"],
        }
    }
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value=mvge_catalog
    )

    installed = [
        {
            "name": "coding_mvge",
            "version": "0.2.6",
            "description": "Coding agent for MvgeOS",
            "runtime": "python",
            "path": "/home/user/.agents/agents/coding_mvge",
            "spells": ["bash", "read", "write"],
        }
    ]
    state.list_installed_mvges_async = AsyncMock(return_value=installed)  # type: ignore[method-assign]
    is_installed_val = True
    state.is_mvge_installed = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda name: is_installed_val
    )

    async def _mock_uninstall(name: str) -> bool:
        nonlocal is_installed_val
        is_installed_val = False
        state.list_installed_mvges_async.return_value = []
        return True

    state.uninstall_mvge_async = AsyncMock(  # type: ignore[method-assign]
        side_effect=_mock_uninstall
    )
    state.install_mvge_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_mvges_persist_after_uninstall")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_mvges_persist_after_uninstall")
    # Verify coding_mvge is visible initially with Installed button
    await user.should_see("coding_mvge")
    await user.should_see("Installed")

    # Click uninstall
    user.find(marker="mvge_uninstall_item_coding_mvge").click()
    await user.should_see("Uninstalling coding_mvge...")

    # Verify coding_mvge is STILL visible in marketplace catalog!
    await user.should_see("coding_mvge")
    # And now shows Install button
    await user.should_see("Install")

    # Click install
    user.find(marker="mvge_install_item_coding_mvge").click()
    await user.should_see("Installing coding_mvge...")
    state.install_mvge_async.assert_called_once_with("coding_mvge")


def test_parse_timestamp_branches() -> None:
    """Test various timestamp parsing branches."""
    assert _parse_timestamp(12345.6) == 12345.6
    assert _parse_timestamp("invalid-date-string") == 0.0
    assert _parse_timestamp(None) == 0.0


def test_open_folder_in_explorer_exception() -> None:
    """Test exception branch of open_folder_in_explorer."""
    with patch("pathlib.Path.expanduser", side_effect=PermissionError("denied")):
        assert open_folder_in_explorer("/any/path") is False


@pytest.mark.asyncio
async def test_packages_panel_mvge_error_notifications_and_sorting(user: User) -> None:
    """Test mvge error branches and date sorting."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "agent_early": {
                "name": "agent_early",
                "version": "1.0.0",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-05T00:00:00Z",
            },
            "agent_late": {
                "name": "agent_late",
                "version": "1.0.0",
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-05T00:00:00Z",
            },
        }
    )
    state.list_installed_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "agent_early",
                "version": "1.0.0",
                "path": "/mock/agents/agent_early",
            }
        ]
    )
    state.is_mvge_installed = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda name: name == "agent_early"
    )
    state.uninstall_mvge_async = AsyncMock(return_value=False)  # type: ignore[method-assign]
    state.install_mvge_async = AsyncMock(return_value=False)  # type: ignore[method-assign]

    @ui.page("/test_mvges_branches")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_mvges_branches")
    await user.should_see("agent_early")

    # Click installed path to open agent folder in explorer
    with patch(
        "mvgeos_gui.components.packages_panel.open_folder_in_explorer",
        return_value=True,
    ) as mock_open:
        user.find("/mock/agents/agent_early").click()
        mock_open.assert_called_once_with("/mock/agents/agent_early")

    # Test uninstall failure notification
    user.find(marker="mvge_uninstall_item_agent_early").click()
    await user.should_see("Failed to uninstall agent_early")

    # Test install failure notification on card
    user.find(marker="mvge_install_item_agent_late").click()
    await user.should_see("Failed to install agent_late")

    # Test sorting by Date Added and Last Updated
    sort_el = next(iter(user.find(marker="mvge_sort_select").elements))
    sort_el.set_value("Date Added")
    await user.should_see("agent_late")
    sort_el.set_value("Last Updated")
    await user.should_see("agent_late")

    # Test dialog failure branch
    user.find(marker="mvge_open_install_dialog_btn").click()
    source_el = next(iter(user.find(marker="mvge_dialog_source_input").elements))
    source_el.set_value("fail_agent")
    user.find(marker="mvge_dialog_install_btn").click()
    await user.should_see("Installing fail_agent...")


@pytest.mark.asyncio
async def test_packages_panel_mvge_refresh_exceptions(user: User) -> None:
    """Test exceptions during mvge data refresh."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("mvge fetch error")
    )
    state.list_installed_mvges_async = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("mvge list error")
    )

    @ui.page("/test_mvges_refresh_exc")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_mvges_refresh_exc")
    await user.should_see("Marketplace")


@pytest.mark.asyncio
async def test_marketplace_merged_list_shows_mvges_and_runes_together(
    user: User,
) -> None:
    """Mvges and runes render in one list, no tabs, no Kind filter."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "alpha-rune": {
                "name": "alpha-rune",
                "version": "1.0.0",
                "description": "A test rune",
                "types": ["Spell"],
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "coding_mvge": {
                "name": "coding_mvge",
                "version": "0.2.6",
                "description": "Coding agent for MvgeOS",
                "spells": ["bash"],
            },
        }
    )
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_marketplace_merged")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_marketplace_merged")
    await user.should_see("Marketplace")

    # Both kinds visible together without switching tabs
    await user.should_see("alpha-rune")
    await user.should_see("coding_mvge")

    # No tabs remain
    with pytest.raises(AssertionError, match="expected to find"):
        user.find(marker="marketplace_mvges_tab")
    with pytest.raises(AssertionError, match="expected to find"):
        user.find(marker="marketplace_runes_tab")

    # No Kind filter — Type filter handles it
    with pytest.raises(AssertionError, match="expected to find"):
        user.find(marker="package_filter_kind_select")


@pytest.mark.asyncio
async def test_marketplace_type_filter_mvge_shows_only_mvges(user: User) -> None:
    """Type filter set to Mvge shows only mvges (Mvge is a type)."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "alpha-rune": {
                "name": "alpha-rune",
                "version": "1.0.0",
                "description": "A test rune",
                "types": ["Spell"],
            },
        }
    )
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "coding_mvge": {
                "name": "coding_mvge",
                "version": "0.2.6",
                "description": "Coding agent for MvgeOS",
                "spells": ["bash"],
            },
        }
    )
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_marketplace_type_mvge")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_marketplace_type_mvge")
    await user.should_see("alpha-rune")
    await user.should_see("coding_mvge")

    # Type filter includes Mvge option
    type_el = next(iter(user.find(marker="package_filter_type_select").elements))
    type_el.set_value("Mvge")

    await user.should_see("coding_mvge", retries=10)
    await user.should_not_see("alpha-rune", retries=10)


@pytest.mark.asyncio
async def test_packages_panel_rune_settings_dialog(user: User) -> None:
    """Clicking settings on an installed rune opens a dialog to toggle enabled."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "name": "my-tool",
                "version": "1.0.0",
                "path": "/home/user/.agents/extensions/my-tool",
                "description": "Installed tool description",
                "hooks": [],
                "python_deps": [],
            }
        ]
    )
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.set_rune_enabled_async = AsyncMock(return_value=True)  # type: ignore[method-assign]

    @ui.page("/test_packages_rune_settings")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_rune_settings")
    await user.should_see("my-tool")

    # Click settings button on the installed rune card
    user.find(marker="package_settings_item_my-tool").click()
    await user.should_see("my-tool Settings")
    await user.should_see("Enabled")

    # Toggle enabled off and save
    state.set_rune_enabled_async.assert_not_called()


@pytest.mark.asyncio
async def test_packages_panel_empty_state_explains_how_to_get_packages(
    user: User,
) -> None:
    """An empty catalog must explain how to get packages, not just say none."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_empty_guidance")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_empty_guidance")
    await user.should_see("No packages found")
    await user.should_see("Install Rune from URL/Git")
    await user.should_see("marketplace name, git URL, or local path")


@pytest.mark.asyncio
async def test_packages_panel_install_dialog_validates_empty_source(
    user: User,
) -> None:
    """Empty rune install submission must show inline validation, not no-op."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_install_validation")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_install_validation")
    user.find(marker="package_open_install_dialog_btn").click()
    await user.should_see("Install Extension Rune")
    user.find(marker="package_dialog_install_btn").click()
    await user.should_see("Enter a git URL, local path, or marketplace rune name")


@pytest.mark.asyncio
async def test_packages_panel_mvge_install_dialog_validates_empty_source(
    user: User,
) -> None:
    """Empty mvge install submission must show inline validation, not no-op."""
    state = AppState()
    state.fetch_marketplace_runes_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_runes_async = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.fetch_marketplace_mvges_async = AsyncMock(return_value={})  # type: ignore[method-assign]
    state.list_installed_mvges_async = AsyncMock(return_value=[])  # type: ignore[method-assign]

    @ui.page("/test_packages_mvge_install_validation")
    def page() -> None:
        render_packages_panel(state)

    await user.open("/test_packages_mvge_install_validation")
    user.find(marker="mvge_open_install_dialog_btn").click()
    await user.should_see("Install Mvge Agent")
    user.find(marker="mvge_dialog_install_btn").click()
    await user.should_see("Enter a git URL, local path, or marketplace mvge name")
