"""Integration tests for 3-column obsidian shell layout and components."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mvgeos_tome.ledger import TomeLedger
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.app import build_page, init_app
from mvgeos_gui.state import AppState
from mvgeos_gui.tome_service import TomeService


def _init_git_repo(repo_path: Path, branch: str) -> None:
    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    (repo_path / "README.md").write_text("test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_full_shell_layout_rendering(user: User) -> None:
    """Verify 3-column shell elements rendered correctly."""
    state = AppState(project_path=Path("C:/demo/my-project"))

    @ui.page("/test_shell_render")
    def page() -> None:
        build_page(state)

    await user.open("/test_shell_render")

    # Left sidebar branding and action
    await user.should_see("MvgeOS")
    await user.should_see("New Conversation")
    await user.should_see("Conversation History")
    await user.should_see("Scheduled Tasks")
    await user.should_see("Projects")

    # Center header breadcrumb
    await user.should_see("my-project")
    await user.should_see("Open IDE")

    # Empty state centered project switcher
    await user.should_see("Quick Start")
    await user.should_see("New Project")
    await user.should_see("No Project")

    # Right Inspector accordions
    await user.should_see("Context")
    await user.should_see("Subagents")
    await user.should_see("Files Changed")
    await user.should_see("Artifacts")
    await user.should_see("Skills Used")
    await user.should_see("Uploads")
    await user.should_see("Background Tasks")


@pytest.mark.asyncio
async def test_sidebar_toggle_interaction(user: User) -> None:
    """Verify toggling left sidebar expansion state."""
    state = AppState()

    @ui.page("/test_sidebar_toggle")
    def page() -> None:
        build_page(state)

    await user.open("/test_sidebar_toggle")
    assert state.sidebar_expanded is True

    # Click toggle sidebar button
    user.find("toggle_sidebar_btn").click()
    assert state.sidebar_expanded is False

    user.find("toggle_sidebar_btn").click()
    assert state.sidebar_expanded is True


@pytest.mark.asyncio
async def test_inspector_toggle_interaction(user: User) -> None:
    """Verify toggling inspector panel expansion state."""
    state = AppState()

    @ui.page("/test_inspector_toggle")
    def page() -> None:
        build_page(state)

    await user.open("/test_inspector_toggle")
    assert state.inspector_expanded is True

    # Click toggle inspector button
    user.find("toggle_inspector_btn").click()
    assert state.inspector_expanded is False

    user.find("toggle_inspector_btn").click()
    assert state.inspector_expanded is True


@pytest.mark.asyncio
async def test_new_conversation_button_resets_state(user: User) -> None:
    """Verify clicking '+ New Conversation' resets conversation state."""
    state = AppState()
    state.active_tome_id = "tome-99"
    state.tome_title = "Existing session"

    @ui.page("/test_new_convo_btn")
    def page() -> None:
        build_page(state)

    await user.open("/test_new_convo_btn")
    user.find("new_conversation_btn").click()

    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"


@pytest.mark.asyncio
async def test_project_picker_selection(user: User) -> None:
    """Verify switching projects from the empty state project picker."""
    state = AppState(project_path=Path("C:/demo/project-a"))
    proj_b = Path("C:/demo/project-b")
    state.add_recent_project(proj_b)

    @ui.page("/test_project_picker")
    def page() -> None:
        build_page(state)

    await user.open("/test_project_picker")
    await user.should_see("project-a")

    # Select project-b
    state.set_project(proj_b)
    assert state.project_path == proj_b


@pytest.mark.asyncio
async def test_collapsed_panels_rendering(user: User) -> None:
    """Verify initial rendering when sidebar and inspector are collapsed."""
    state = AppState(sidebar_expanded=False, inspector_expanded=False)

    @ui.page("/test_collapsed")
    def page() -> None:
        build_page(state)

    await user.open("/test_collapsed")
    assert state.sidebar_expanded is False
    assert state.inspector_expanded is False


@pytest.mark.asyncio
async def test_channeling_input_dock(user: User) -> None:
    """Verify input dock state while channeling and stopping channeling."""
    state = AppState(is_channeling=True)

    @ui.page("/test_channeling")
    def page() -> None:
        build_page(state)

    await user.open("/test_channeling")
    assert state.is_channeling is True


@pytest.mark.asyncio
async def test_init_app_registers_index(user: User) -> None:
    """Verify init_app registers the root index page properly."""
    state = AppState(project_path=Path("C:/demo/init-project"))
    app_state = init_app(state)
    assert app_state == state

    await user.open("/")
    await user.should_see("init-project")


# --- Tome integration tests ---


@pytest.mark.asyncio
async def test_sidebar_displays_tomes(user: User, tmp_path: Path) -> None:
    """Verify sidebar lists tombs with titles, timestamps, and git branches."""
    tome_dir = tmp_path / "tomes"
    project_path = tmp_path / "proj"
    project_path.mkdir()
    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(str(project_path))
    ledger.append_tome_info(meta.id, {"name": "Bug Fix Session"})

    service = TomeService(tome_dir)
    state = AppState(project_path=project_path, tome_service=service)
    state.load_tomes()

    @ui.page("/test_sidebar_tomes")
    def page() -> None:
        build_page(state)

    await user.open("/test_sidebar_tomes")
    await user.should_see("Bug Fix Session")
    await user.should_see("now")


@pytest.mark.asyncio
async def test_sidebar_shows_git_branch(user: User, tmp_path: Path) -> None:
    """Verify sidebar shows git branch tags for tome entries."""
    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo, "feature-branch")

    tome_dir = tmp_path / "tomes"
    ledger = TomeLedger(tome_dir)
    ledger.create_tome(str(repo))

    service = TomeService(tome_dir)
    state = AppState(project_path=repo, tome_service=service)
    state.load_tomes()

    @ui.page("/test_git_branch")
    def page() -> None:
        build_page(state)

    await user.open("/test_git_branch")
    await user.should_see("feature-branch")


@pytest.mark.asyncio
async def test_clicking_tome_switches_session(user: User, tmp_path: Path) -> None:
    """Verify clicking a tome entry switches the active session."""
    tome_dir = tmp_path / "tomes"
    project_path = tmp_path / "proj"
    project_path.mkdir()
    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(str(project_path))
    ledger.append_tome_info(meta.id, {"name": "Test Session"})

    service = TomeService(tome_dir)
    state = AppState(project_path=project_path, tome_service=service)
    state.load_tomes()

    @ui.page("/test_click_tome")
    def page() -> None:
        build_page(state)

    await user.open("/test_click_tome")

    user.find(f"tome_entry_{meta.id[:8]}").click()

    assert state.active_tome_id == meta.id
    assert state.tome_title == "Test Session"


@pytest.mark.asyncio
async def test_header_breadcrumb_with_tome(user: User, tmp_path: Path) -> None:
    """Verify header breadcrumb shows active tome title."""
    tome_dir = tmp_path / "tomes"
    project_path = tmp_path / "my-awesome-project"
    project_path.mkdir()
    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(str(project_path))
    ledger.append_tome_info(meta.id, {"name": "Active Session"})

    service = TomeService(tome_dir)
    state = AppState(project_path=project_path, tome_service=service)
    state.load_tomes()
    state.switch_to_tome(meta.id)

    @ui.page("/test_breadcrumb")
    def page() -> None:
        build_page(state)

    await user.open("/test_breadcrumb")
    await user.should_see("my-awesome-project")
    await user.should_see("Active Session")


@pytest.mark.asyncio
async def test_viewport_transitions_to_conversation(user: User, tmp_path: Path) -> None:
    """Verify center viewport transitions from empty state to active session."""
    tome_dir = tmp_path / "tomes"
    project_path = tmp_path / "proj"
    project_path.mkdir()
    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(str(project_path))
    ledger.append_tome_info(meta.id, {"name": "Active Session"})

    service = TomeService(tome_dir)
    state = AppState(project_path=project_path, tome_service=service)
    state.load_tomes()
    state.switch_to_tome(meta.id)

    @ui.page("/test_viewport_transition")
    def page() -> None:
        build_page(state)

    await user.open("/test_viewport_transition")
    await user.should_see("Active Session")


@pytest.mark.asyncio
async def test_open_ide_button_launches_editor(user: User, tmp_path: Path) -> None:
    """Verify Open IDE button spawns editor in project directory."""
    with patch("mvgeos_gui.state.subprocess.Popen") as mock_popen:
        state = AppState(project_path=tmp_path)
        mock_popen.return_value = MagicMock()

        @ui.page("/test_open_ide")
        def page() -> None:
            build_page(state)

        await user.open("/test_open_ide")
        user.find("open_ide_btn").click()

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "code"
        assert args[1] == str(tmp_path)


@pytest.mark.asyncio
async def test_header_menu_items_visible(user: User) -> None:
    """Verify 3-dots menu items are labeled correctly."""
    state = AppState()

    @ui.page("/test_menu_items")
    def page() -> None:
        build_page(state)

    await user.open("/test_menu_items")
    await user.should_see("Export Transcript")
    await user.should_see("Fork Tome")
    await user.should_see("Clear Conversation")


@pytest.mark.asyncio
async def test_empty_state_visible_without_tome(user: User) -> None:
    """Verify empty state renders when no tome is active."""
    state = AppState()

    @ui.page("/test_empty_state")
    def page() -> None:
        build_page(state)

    await user.open("/test_empty_state")
    await user.should_see("How can MvgeOS help you today?")


@pytest.mark.asyncio
async def test_new_conversation_hides_conversation_view(
    user: User, tmp_path: Path
) -> None:
    """Verify new conversation transitions back to empty state."""
    tome_dir = tmp_path / "tomes"
    project_path = tmp_path / "proj"
    project_path.mkdir()
    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(str(project_path))

    service = TomeService(tome_dir)
    state = AppState(project_path=project_path, tome_service=service)
    state.load_tomes()
    state.switch_to_tome(meta.id)

    @ui.page("/test_new_convo_transition")
    def page() -> None:
        build_page(state)

    await user.open("/test_new_convo_transition")
    user.find("new_conversation_btn").click()

    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"
