"""Unit tests for AppState management in mvgeos-gui."""

from pathlib import Path

from mvgeos_gui.state import AppState


def test_app_state_defaults() -> None:
    """Verify default initial values for AppState."""
    state = AppState()
    assert state.project_path == Path.cwd()
    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"
    assert state.sidebar_expanded is True
    assert state.inspector_expanded is True
    assert state.selected_model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert state.is_channeling is False
    assert isinstance(state.recent_projects, list)


def test_app_state_custom_init() -> None:
    """Verify custom initialization options for AppState."""
    custom_path = Path("/custom/project")
    state = AppState(
        project_path=custom_path,
        selected_model="custom/model",
        sidebar_expanded=False,
        inspector_expanded=False,
    )
    assert state.project_path == custom_path
    assert state.selected_model == "custom/model"
    assert state.sidebar_expanded is False
    assert state.inspector_expanded is False
    assert custom_path in state.recent_projects


def test_toggle_sidebar() -> None:
    """Verify toggling sidebar expansion state."""
    state = AppState()
    assert state.sidebar_expanded is True
    state.toggle_sidebar()
    assert state.sidebar_expanded is False
    state.toggle_sidebar()
    assert state.sidebar_expanded is True


def test_toggle_inspector() -> None:
    """Verify toggling inspector expansion state."""
    state = AppState()
    assert state.inspector_expanded is True
    state.toggle_inspector()
    assert state.inspector_expanded is False
    state.toggle_inspector()
    assert state.inspector_expanded is True


def test_set_project() -> None:
    """Verify switching active workspace project path."""
    state = AppState(project_path=Path("/initial/dir"))
    new_dir = Path("/new/project/dir")
    state.set_project(new_dir)
    assert state.project_path == new_dir
    assert new_dir in state.recent_projects
    assert state.recent_projects[0] == new_dir


def test_add_recent_project_deduplication_and_ordering() -> None:
    """Verify recent projects are deduplicated and newest is first."""
    state = AppState()
    p1 = Path("/path/one")
    p2 = Path("/path/two")
    state.add_recent_project(p1)
    state.add_recent_project(p2)
    assert state.recent_projects[0] == p2
    assert state.recent_projects[1] == p1

    # Adding p1 again moves it to index 0
    state.add_recent_project(p1)
    assert state.recent_projects[0] == p1
    assert state.recent_projects.count(p1) == 1


def test_recent_projects_max_limit() -> None:
    """Verify recent projects list is capped at 10 items."""
    state = AppState()
    for i in range(15):
        state.add_recent_project(Path(f"/path/{i}"))
    assert len(state.recent_projects) == 10
    assert state.recent_projects[0] == Path("/path/14")


def test_new_conversation() -> None:
    """Verify resetting conversation session state."""
    state = AppState()
    state.active_tome_id = "tome-123"
    state.tome_title = "Refactoring loop"
    state.is_channeling = True

    state.new_conversation()
    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"
    assert state.is_channeling is False


def test_listeners_and_exception_handling() -> None:
    """Verify subscriptions and safe exception swallowing in notify."""
    state = AppState()
    called: list[str] = []

    def good_listener() -> None:
        called.append("good")

    def failing_listener() -> None:
        raise RuntimeError("boom")

    state.subscribe(good_listener)
    state.subscribe(good_listener)  # idempotent
    state.subscribe(failing_listener)

    state.notify()
    assert called == ["good"]
