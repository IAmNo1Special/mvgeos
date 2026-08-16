"""Unit tests for AppState management in mvgeos-gui."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_tome.ledger import TomeLedger

from mvgeos_gui.models import ChangedFile, ChatMessage, DiffView
from mvgeos_gui.state import AppState
from mvgeos_gui.tome_service import TomeService


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
    assert state.tome_service is not None
    assert state.loaded_tomes == []
    assert state.messages == []
    assert state.total_mana_used == 0
    assert state.pending_attachments == []


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
    state.messages.append(ChatMessage(role="user", content="hello"))
    state.total_mana_used = 500

    state.new_conversation()
    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"
    assert state.is_channeling is False
    assert state.messages == []
    assert state.total_mana_used == 0


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


def test_switch_model() -> None:
    """Verify switching active Realm model updates state and notifies."""
    state = AppState()
    called: list[bool] = []
    state.subscribe(lambda: called.append(True))

    state.switch_model("anthropic/claude-3-5-sonnet")
    assert state.selected_model == "anthropic/claude-3-5-sonnet"
    assert called == [True]


def test_set_message_feedback() -> None:
    """Verify setting and toggling message feedback status."""
    state = AppState()
    msg = ChatMessage(role="assistant", content="Response")
    state.messages.append(msg)

    # Set up
    state.set_message_feedback(0, "up")
    assert msg.feedback == "up"

    # Toggling same feedback clears it
    state.set_message_feedback(0, "up")
    assert msg.feedback is None

    # Setting down
    state.set_message_feedback(0, "down")
    assert msg.feedback == "down"

    # Out of range is safe no-op
    state.set_message_feedback(99, "up")


@pytest.mark.asyncio
async def test_submit_prompt_appends_messages_and_starts_task() -> None:
    """Verify submit_prompt creates user and assistant messages."""
    state = AppState()
    mock_service = MagicMock()
    mock_service.run_prompt = AsyncMock()
    state.agent_service = mock_service

    state.submit_prompt("Build a widget")
    assert len(state.messages) == 2
    assert state.messages[0].role == "user"
    assert state.messages[0].content == "Build a widget"
    assert state.messages[1].role == "assistant"
    assert state.messages[1].is_streaming is True
    assert state.is_channeling is True

    # Empty prompt is a no-op
    state.submit_prompt("")
    assert len(state.messages) == 2


def test_stop_channeling_cancels_active_task() -> None:
    """Verify stop_channeling marks streaming as false and resets channeling state."""
    state = AppState()
    msg = ChatMessage(role="assistant", is_streaming=True)
    state.messages.append(msg)
    state.is_channeling = True

    mock_task = MagicMock()
    state.active_task = mock_task
    mock_service = MagicMock()
    state.agent_service = mock_service

    state.stop_channeling()
    assert state.is_channeling is False
    assert msg.is_streaming is False
    mock_task.cancel.assert_called_once()
    mock_service.cancel.assert_called_once()


# --- Tome service integration tests ---


def _make_state_with_tomes(
    project_cwd: str = "/test/project",
) -> tuple[AppState, Path]:
    """Create AppState backed by a temp tome dir with no tombs yet."""
    tmp_dir = tempfile.mkdtemp()
    tome_dir = Path(tmp_dir)
    service = TomeService(tome_dir)
    state = AppState(project_path=Path(project_cwd), tome_service=service)
    return state, tome_dir


def _create_tome(tome_dir: Path, cwd: str, tome_id: str | None = None) -> str:
    ledger = TomeLedger(tome_dir)
    meta = ledger.create_tome(cwd, tome_id=tome_id)
    return meta.id


class TestLoadTomes:
    def test_loads_tomes_for_active_project(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        _create_tome(tome_dir, "/proj/a")
        _create_tome(tome_dir, "/proj/b")

        state.load_tomes()

        assert len(state.loaded_tomes) == 1
        assert state.loaded_tomes[0].tome_id is not None

    def test_filters_out_other_projects(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        _create_tome(tome_dir, "/proj/a")
        _create_tome(tome_dir, "/proj/b")

        state.load_tomes()

        assert len(state.loaded_tomes) == 1

    def test_empty_when_no_tomes(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")

        state.load_tomes()

        assert state.loaded_tomes == []

    def test_sets_active_flag_on_loaded_tomes(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        state.active_tome_id = tome_id

        state.load_tomes()

        active_entries = [e for e in state.loaded_tomes if e.is_active]
        assert len(active_entries) == 1
        assert active_entries[0].tome_id == tome_id

    def test_notifies_listeners(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        _create_tome(tome_dir, "/proj/a")

        state.load_tomes()

        assert called == [True]


class TestSwitchToTome:
    def test_sets_active_tome_id_and_title(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        ledger = TomeLedger(tome_dir)
        ledger.append_tome_info(tome_id, {"name": "Bug Fix Session"})

        state.switch_to_tome(tome_id)

        assert state.active_tome_id == tome_id
        assert state.tome_title == "Bug Fix Session"

    def test_loads_existing_messages_from_tome(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        ledger = TomeLedger(tome_dir)
        ledger.append_message(tome_id, "user", "How do I fix this?")
        ledger.append_message(tome_id, "assistant", "Here is the fix.")

        state.switch_to_tome(tome_id)

        assert len(state.messages) == 2
        assert state.messages[0].content == "How do I fix this?"
        assert state.messages[1].content == "Here is the fix."

    def test_sets_title_from_tome_info_title_key(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        ledger = TomeLedger(tome_dir)
        ledger.append_tome_info(tome_id, {"title": "Refactor Loop"})

        state.switch_to_tome(tome_id)

        assert state.tome_title == "Refactor Loop"

    def test_title_fallback_conversation(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")

        state.switch_to_tome(tome_id)

        assert state.tome_title == "Conversation"

    def test_clears_channeling(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        state.is_channeling = True
        tome_id = _create_tome(tome_dir, "/proj/a")

        state.switch_to_tome(tome_id)

        assert state.is_channeling is False

    def test_unknown_tome_id_is_noop(self) -> None:
        state, _ = _make_state_with_tomes("/proj/a")
        state.active_tome_id = None
        state.tome_title = "New Conversation"

        state.switch_to_tome("nonexistent_tome_id")

        assert state.active_tome_id is None
        assert state.tome_title == "New Conversation"

    def test_notifies_listeners(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        tome_id = _create_tome(tome_dir, "/proj/a")

        state.switch_to_tome(tome_id)

        assert called == [True]


class TestForkTome:
    def test_forks_active_tome_and_switches(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        ledger = TomeLedger(tome_dir)
        entry = ledger.append_message(tome_id, "user", "hello")
        ledger.append_leaf(tome_id, entry.id)
        state.active_tome_id = tome_id
        state.tome_title = "Original"

        forked_id = state.fork_tome()

        assert forked_id is not None
        assert state.active_tome_id == forked_id
        assert state.active_tome_id != tome_id

    def test_no_active_tome_returns_none(self) -> None:
        state, _ = _make_state_with_tomes("/proj/a")

        assert state.fork_tome() is None

    def test_no_leaf_returns_none(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        state.active_tome_id = tome_id

        assert state.fork_tome() is None


class TestExportTome:
    def test_exports_to_project_dir(self) -> None:
        with tempfile.TemporaryDirectory() as proj_tmp:
            state, tome_dir = _make_state_with_tomes(proj_tmp)
            tome_id = _create_tome(tome_dir, proj_tmp)
            ledger = TomeLedger(tome_dir)
            ledger.append_message(tome_id, "user", "hello")
            ledger.append_message(tome_id, "assistant", "hi")
            state.active_tome_id = tome_id

            result = state.export_tome()

            assert result is not None
            assert result.suffix == ".jsonl"
            assert result.exists()

    def test_no_active_tome_returns_none(self) -> None:
        state, _ = _make_state_with_tomes("/proj/a")

        assert state.export_tome() is None

    def test_export_filename_uses_short_id(self) -> None:
        with tempfile.TemporaryDirectory() as proj_tmp:
            state, tome_dir = _make_state_with_tomes(proj_tmp)
            tome_id = _create_tome(tome_dir, proj_tmp)
            state.active_tome_id = tome_id

            result = state.export_tome()

            assert result is not None
            assert result.name == f"{tome_id[:8]}.jsonl"


class TestClearHistory:
    def test_resets_conversation_state(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        state.active_tome_id = tome_id
        state.tome_title = "Old Session"
        state.is_channeling = True

        state.clear_history()

        assert state.active_tome_id is None
        assert state.tome_title == "New Conversation"
        assert state.is_channeling is False

    def test_notifies_listeners(self) -> None:
        state, _ = _make_state_with_tomes("/proj/a")
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))

        state.clear_history()

        assert called == [True]


class TestSetProjectReloadsTomes:
    def test_set_project_loads_tomes_for_new_project(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        _create_tome(tome_dir, "/proj/b")

        state.set_project(Path("/proj/b"))

        assert len(state.loaded_tomes) == 1


# --- Attachment tests ---


class TestPendingAttachments:
    def test_add_attachment_appends(self) -> None:
        state = AppState()
        state.add_attachment("main.py")
        state.add_attachment("utils.py")
        assert state.pending_attachments == ["main.py", "utils.py"]

    def test_add_attachment_deduplicates(self) -> None:
        state = AppState()
        state.add_attachment("main.py")
        state.add_attachment("main.py")
        assert state.pending_attachments == ["main.py"]

    def test_add_attachment_empty_is_noop(self) -> None:
        state = AppState()
        state.add_attachment("")
        assert state.pending_attachments == []

    def test_add_attachment_notifies_listeners(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.add_attachment("main.py")
        assert called == [True]

    def test_remove_attachment_by_index(self) -> None:
        state = AppState()
        state.pending_attachments = ["a.py", "b.py", "c.py"]
        state.remove_attachment(1)
        assert state.pending_attachments == ["a.py", "c.py"]

    def test_remove_attachment_out_of_range_safe(self) -> None:
        state = AppState()
        state.pending_attachments = ["a.py"]
        state.remove_attachment(99)
        assert state.pending_attachments == ["a.py"]
        state.remove_attachment(-1)
        assert state.pending_attachments == ["a.py"]

    def test_remove_attachment_notifies_listeners(self) -> None:
        state = AppState()
        state.pending_attachments = ["a.py", "b.py"]
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.remove_attachment(0)
        assert called == [True]

    def test_clear_attachments(self) -> None:
        state = AppState()
        state.pending_attachments = ["a.py", "b.py"]
        state.clear_attachments()
        assert state.pending_attachments == []

    def test_clear_attachments_empty_is_noop(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.clear_attachments()
        assert state.pending_attachments == []
        assert called == []

    def test_set_project_clears_attachments(self) -> None:
        state = AppState(project_path=Path("/proj/a"))
        state.pending_attachments = ["a.py"]
        state.set_project(Path("/proj/b"))
        assert state.pending_attachments == []


class TestSubmitPromptAttachments:
    def test_submit_prompt_binds_attachments_to_message(self) -> None:
        state = AppState()
        state.pending_attachments = ["file1.py", "file2.py"]
        mock_service = MagicMock()
        mock_service.run_prompt = AsyncMock()
        state.agent_service = mock_service

        state.submit_prompt("Analyze these files")

        user_msg = state.messages[0]
        assert user_msg.attachments == ["file1.py", "file2.py"]

    def test_submit_prompt_clears_pending_attachments(self) -> None:
        state = AppState()
        state.pending_attachments = ["file1.py"]
        mock_service = MagicMock()
        mock_service.run_prompt = AsyncMock()
        state.agent_service = mock_service

        state.submit_prompt("Hello")

        assert state.pending_attachments == []

    def test_submit_prompt_empty_no_attachments_bound(self) -> None:
        state = AppState()
        state.pending_attachments = ["file1.py"]

        state.submit_prompt("")

        assert state.pending_attachments == ["file1.py"]
        assert state.messages == []

    def test_submit_prompt_no_attachments_field_empty(self) -> None:
        state = AppState()
        mock_service = MagicMock()
        mock_service.run_prompt = AsyncMock()
        state.agent_service = mock_service

        state.submit_prompt("Hello")

        user_msg = state.messages[0]
        assert user_msg.attachments == []

    def test_new_conversation_clears_attachments(self) -> None:
        state = AppState()
        state.pending_attachments = ["file1.py"]
        state.new_conversation()
        assert state.pending_attachments == []

    def test_clear_history_clears_attachments(self) -> None:
        state = AppState()
        state.pending_attachments = ["file1.py"]
        state.clear_history()
        assert state.pending_attachments == []


# --- Active skills tests ---


def _make_manifest(
    name: str = "review",
    path: str = "/skills/review/SKILL.md",
    scope: str = "project",
    description: str = "Review code",
) -> Any:
    """Build a minimal SkillManifest for testing."""
    from mvgeos_runes.types import SkillManifest, SkillScope

    return SkillManifest(
        name=name,
        description=description,
        scope=SkillScope(scope),
        path=path,
    )


def test_active_skills_default_empty() -> None:
    """Verify active_skills defaults to an empty list."""
    state = AppState()
    assert state.active_skills == []


def test_skill_info_from_manifest() -> None:
    """Verify SkillInfo is derived from a SkillManifest correctly."""
    state = AppState()
    manifest = _make_manifest(
        name="review",
        path="/skills/review/SKILL.md",
        scope="user",
        description="Review code",
    )
    info = state.skill_info_from_manifest(manifest)
    assert info.name == "review"
    assert info.description == "Review code"
    assert info.scope == "user"
    assert info.path == "/skills/review/SKILL.md"
    assert info.invoked is False


def test_add_skill_appends_and_notifies() -> None:
    """Verify add_skill appends a new skill and notifies listeners."""
    state = AppState()
    called: list[bool] = []
    state.subscribe(lambda: called.append(True))

    manifest = _make_manifest()
    added = state.add_skill(manifest)
    assert added is True
    assert len(state.active_skills) == 1
    assert state.active_skills[0].name == "review"
    assert called == [True]


def test_add_skill_deduplicates() -> None:
    """Verify add_skill does not duplicate an existing skill by name."""
    state = AppState()
    manifest = _make_manifest()
    state.add_skill(manifest)
    state.add_skill(manifest)
    assert len(state.active_skills) == 1


def test_add_skill_returns_false_when_present() -> None:
    """Verify add_skill returns False when the skill is already tracked."""
    state = AppState()
    manifest = _make_manifest()
    state.add_skill(manifest)
    assert state.add_skill(manifest) is False


def test_remove_skill_by_name() -> None:
    """Verify remove_skill removes a skill by name."""
    state = AppState()
    state.add_skill(_make_manifest(name="review"))
    state.add_skill(_make_manifest(name="lint", path="/skills/lint/SKILL.md"))
    removed = state.remove_skill("review")
    assert removed is True
    assert [s.name for s in state.active_skills] == ["lint"]


def test_remove_skill_unknown_is_safe() -> None:
    """Verify remove_skill is a safe no-op for unknown names."""
    state = AppState()
    state.add_skill(_make_manifest())
    assert state.remove_skill("nonexistent") is False
    assert len(state.active_skills) == 1


def test_remove_skill_notifies_listeners() -> None:
    """Verify remove_skill notifies listeners when a skill is removed."""
    state = AppState()
    state.add_skill(_make_manifest())
    called: list[bool] = []
    state.subscribe(lambda: called.append(True))
    state.remove_skill("review")
    assert called == [True]


def test_clear_skills_removes_all() -> None:
    """Verify clear_skills empties the active_skills list."""
    state = AppState()
    state.add_skill(_make_manifest(name="review"))
    state.add_skill(_make_manifest(name="lint", path="/skills/lint/SKILL.md"))
    state.clear_skills()
    assert state.active_skills == []


def test_clear_skills_empty_is_noop() -> None:
    """Verify clear_skills does not notify when there are no skills."""
    state = AppState()
    called: list[bool] = []
    state.subscribe(lambda: called.append(True))
    state.clear_skills()
    assert called == []


def test_new_conversation_clears_skills() -> None:
    """Verify new_conversation resets active_skills."""
    state = AppState()
    state.add_skill(_make_manifest())
    state.new_conversation()
    assert state.active_skills == []


class TestChangedFiles:
    def test_default_changed_files_empty(self) -> None:
        """Verify changed_files defaults to empty list."""
        state = AppState()
        assert state.changed_files == []

    def test_refresh_changed_files_updates_state(self) -> None:
        """Verify refresh_changed_files updates changed_files from git."""
        state = AppState()
        changed = [
            ChangedFile(
                path="src/main.py",
                status="modified",
                additions=1,
                deletions=0,
            ),
        ]
        with patch("mvgeos_gui.state.get_changed_files", return_value=changed):
            state.refresh_changed_files()
        assert len(state.changed_files) == 1
        assert state.changed_files[0].path == "src/main.py"

    def test_refresh_changed_files_notifies_listeners(self) -> None:
        """Verify refresh_changed_files notifies listeners."""
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        with patch("mvgeos_gui.state.get_changed_files", return_value=[]):
            state.refresh_changed_files()
        assert called == [True]

    def test_open_diff_review_sets_selected_path(self) -> None:
        """Verify open_diff_review sets _selected_diff_path."""
        state = AppState()
        state.open_diff_review("src/main.py")
        assert state._selected_diff_path == "src/main.py"

    def test_open_diff_review_notifies_listeners(self) -> None:
        """Verify open_diff_review notifies listeners."""
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.open_diff_review("src/main.py")
        assert called == [True]

    def test_get_selected_diff_view_returns_none_when_empty(self) -> None:
        """Verify get_selected_diff_view returns None when no path selected."""
        state = AppState()
        assert state.get_selected_diff_view() is None

    def test_get_selected_diff_view_returns_view(self) -> None:
        """Verify get_selected_diff_view returns DiffView for selected path."""
        state = AppState()
        state._selected_diff_path = "src/main.py"
        view = DiffView(
            file_path="src/main.py",
            status="modified",
            additions=1,
            deletions=0,
        )
        with patch("mvgeos_gui.state.get_diff_for_file", return_value=view):
            result = state.get_selected_diff_view()
        assert result is not None
        assert result.file_path == "src/main.py"

    def test_clear_diff_selection_clears_path(self) -> None:
        """Verify clear_diff_selection clears _selected_diff_path."""
        state = AppState()
        state._selected_diff_path = "src/main.py"
        state.clear_diff_selection()
        assert state._selected_diff_path is None

    def test_clear_diff_selection_notifies_listeners(self) -> None:
        """Verify clear_diff_selection notifies listeners."""
        state = AppState()
        state._selected_diff_path = "src/main.py"
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.clear_diff_selection()
        assert called == [True]


class TestSettingsModals:
    def test_open_app_settings_sets_flag(self) -> None:
        state = AppState()
        assert state._show_app_settings is False
        state.open_app_settings()
        assert state._show_app_settings is True

    def test_open_app_settings_closes_workspace(self) -> None:
        state = AppState()
        state._show_workspace_settings = True
        state.open_app_settings()
        assert state._show_workspace_settings is False
        assert state._show_app_settings is True

    def test_close_app_settings_clears_flag(self) -> None:
        state = AppState()
        state._show_app_settings = True
        state.close_app_settings()
        assert state._show_app_settings is False

    def test_open_workspace_settings_sets_flag(self) -> None:
        state = AppState()
        assert state._show_workspace_settings is False
        state.open_workspace_settings()
        assert state._show_workspace_settings is True

    def test_open_workspace_settings_closes_app(self) -> None:
        state = AppState()
        state._show_app_settings = True
        state.open_workspace_settings()
        assert state._show_app_settings is False
        assert state._show_workspace_settings is True

    def test_close_workspace_settings_clears_flag(self) -> None:
        state = AppState()
        state._show_workspace_settings = True
        state.close_workspace_settings()
        assert state._show_workspace_settings is False

    def test_open_app_settings_notifies_listeners(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.open_app_settings()
        assert called == [True]

    def test_open_workspace_settings_notifies_listeners(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.open_workspace_settings()
        assert called == [True]
