"""Unit tests for AppState management in mvgeos-gui."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_tome.handle import TomeHandleFactory
from mvgeos_tome.types import TomeEntry, TomeEntryType

from mvgeos_gui.autocomplete import MentionChip
from mvgeos_gui.models import ChangedFile, ChatMessage, DiffView
from mvgeos_gui.services.tome_service import TomeService
from mvgeos_gui.state import AppState
from mvgeos_gui.transcript import InvocationTranscript


def test_app_state_defaults() -> None:
    """Verify default initial values for AppState."""
    state = AppState()
    assert state.project_path == Path.cwd()
    assert state.active_tome_id is None
    assert state.tome_title == "New Conversation"
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
        inspector_expanded=False,
    )
    assert state.project_path == custom_path
    assert state.selected_model == "custom/model"
    assert state.inspector_expanded is False
    assert custom_path in state.recent_projects


def test_toggle_sidebar() -> None:
    """Verify toggling sidebar visibility state."""
    state = AppState()
    assert state.sidebar_open is True
    state.toggle_sidebar()
    assert state.sidebar_open is False
    state.toggle_sidebar()
    assert state.sidebar_open is True


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
    state.messages.append(InvocationTranscript.for_summoner("hello"))
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
    msg = InvocationTranscript.from_tome_content("Response").message
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
    factory = TomeHandleFactory(tome_dir)
    return factory.create_tome(cwd, tome_id=tome_id).tome_id


def _append_message(
    tome_dir: Path, tome_id: str, role: str, content: str, entry_id: str
) -> TomeEntry:
    entry = TomeEntry(
        id=entry_id,
        parent_id=None,
        type=TomeEntryType.MESSAGE,
        timestamp=1000.0,
        payload={"role": role, "content": content},
    )
    TomeHandleFactory(tome_dir).open_write(tome_id).append(entry)
    return entry


def _append_leaf(tome_dir: Path, tome_id: str, target: str, entry_id: str) -> TomeEntry:
    entry = TomeEntry(
        id=entry_id,
        parent_id=None,
        type=TomeEntryType.LEAF,
        timestamp=1001.0,
        payload={"targetId": target},
    )
    TomeHandleFactory(tome_dir).open_write(tome_id).append(entry)
    return entry


def _append_tome_info(tome_dir: Path, tome_id: str, payload: dict) -> None:
    TomeHandleFactory(tome_dir).open_write(tome_id).append(
        TomeEntry(
            id="info-1",
            parent_id=None,
            type=TomeEntryType.TOME_INFO,
            timestamp=1002.0,
            payload=payload,
        )
    )


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
        _append_tome_info(tome_dir, tome_id, {"name": "Bug Fix Session"})

        state.switch_to_tome(tome_id)

        assert state.active_tome_id == tome_id
        assert state.tome_title == "Bug Fix Session"

    def test_loads_existing_messages_from_tome(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        _append_message(tome_dir, tome_id, "user", "How do I fix this?", "m1")
        _append_message(tome_dir, tome_id, "assistant", "Here is the fix.", "m2")

        state.switch_to_tome(tome_id)

        assert len(state.messages) == 2
        assert state.messages[0].content == "How do I fix this?"
        assert state.messages[1].content == "Here is the fix."

    def test_sets_title_from_tome_info_title_key(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        _append_tome_info(tome_dir, tome_id, {"title": "Refactor Loop"})

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

        assert called == [True, True]


class TestForkTome:
    def test_forks_active_tome_and_switches(self) -> None:
        state, tome_dir = _make_state_with_tomes("/proj/a")
        tome_id = _create_tome(tome_dir, "/proj/a")
        entry = _append_message(tome_dir, tome_id, "user", "hello", "m1")
        _append_leaf(tome_dir, tome_id, entry.id, "l1")
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
            _append_message(tome_dir, tome_id, "user", "hello", "m1")
            _append_message(tome_dir, tome_id, "assistant", "hi", "m2")
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


class TestSelectedMentions:
    def test_add_mention_appends_and_notifies(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        chip = MentionChip(text="@main.py", kind="file", icon="code")
        state.add_mention(chip)
        assert state.selected_mentions == [chip]
        assert called == [True]

    def test_remove_last_mention_removes_recent(self) -> None:
        state = AppState()
        state.selected_mentions = [
            MentionChip(text="@a.py", kind="file"),
            MentionChip(text="/help", kind="slash"),
        ]
        state.remove_last_mention()
        assert len(state.selected_mentions) == 1
        assert state.selected_mentions[0].text == "@a.py"

    def test_remove_last_mention_empty_is_noop(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.remove_last_mention()
        assert state.selected_mentions == []
        assert called == []

    def test_clear_mentions_empties_list(self) -> None:
        state = AppState()
        state.selected_mentions = [
            MentionChip(text="@a.py", kind="file"),
            MentionChip(text="/help", kind="slash"),
        ]
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.clear_mentions()
        assert state.selected_mentions == []
        assert called == [True]

    def test_clear_mentions_empty_is_noop(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.clear_mentions()
        assert state.selected_mentions == []
        assert called == []

    def test_submit_prompt_prepends_mentions(self) -> None:
        state = AppState()
        state.selected_mentions = [
            MentionChip(text="@main.py", kind="file"),
            MentionChip(text="/help", kind="slash"),
        ]
        mock_service = MagicMock()
        mock_service.run_prompt = AsyncMock()
        state.agent_service = mock_service

        state.submit_prompt("Analyze this")

        user_msg = state.messages[0]
        assert user_msg.content == "@main.py /help Analyze this"
        assert state.selected_mentions == []

    def test_submit_prompt_mentions_only(self) -> None:
        state = AppState()
        state.selected_mentions = [
            MentionChip(text="@main.py", kind="file"),
        ]
        mock_service = MagicMock()
        mock_service.run_prompt = AsyncMock()
        state.agent_service = mock_service

        state.submit_prompt("")

        user_msg = state.messages[0]
        assert user_msg.content == "@main.py"
        assert state.selected_mentions == []

    def test_submit_prompt_no_mentions(self) -> None:
        state = AppState()
        mock_service = MagicMock()
        mock_service.run_prompt = AsyncMock()
        state.agent_service = mock_service

        state.submit_prompt("Hello world")

        user_msg = state.messages[0]
        assert user_msg.content == "Hello world"
        assert state.selected_mentions == []

    def test_new_conversation_clears_mentions(self) -> None:
        state = AppState()
        state.selected_mentions = [MentionChip(text="@a.py", kind="file")]
        state.new_conversation()
        assert state.selected_mentions == []

    def test_set_project_clears_mentions(self) -> None:
        state = AppState(project_path=Path("/proj/a"))
        state.selected_mentions = [MentionChip(text="@a.py", kind="file")]
        state.set_project(Path("/proj/b"))
        assert state.selected_mentions == []


# --- Active skills tests ---


def _make_manifest(
    name: str = "review",
    path: str = "/skills/review/SKILL.md",
    scope: str = "project",
    description: str = "Review code",
) -> Any:
    """Build a minimal SkillManifest for testing."""
    from mvgeos_runes.types import (
        SkillManifest,
        SkillScope,
    )

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

    def test_unsubscribe_listener(self) -> None:
        state = AppState()
        called: list[int] = []

        def listener() -> None:
            called.append(1)

        state.subscribe(listener)
        state.notify()
        assert len(called) == 1
        state.unsubscribe(listener)
        state.notify()
        assert len(called) == 1

    def test_clear_listeners(self) -> None:
        state = AppState()
        called: list[int] = []

        state.subscribe(lambda: called.append(1))
        state.subscribe(lambda: called.append(2))
        assert len(state._change_listeners) == 2
        state.clear_listeners()
        assert len(state._change_listeners) == 0
        state.notify()
        assert called == []

    def test_notify_coroutine_without_running_loop_closes_coroutine(
        self,
    ) -> None:
        import warnings

        state = AppState()
        executed = False

        async def async_listener() -> None:
            nonlocal executed
            executed = True

        state.subscribe(async_listener)
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            state.notify()
            unawaited_warnings = [
                (w.category, str(w.message))
                for w in record
                if issubclass(w.category, RuntimeWarning)
                and "was never awaited" in str(w.message)
            ]
            assert not unawaited_warnings, f"Found unawaited: {unawaited_warnings}"
        assert executed is False

    @pytest.mark.asyncio
    async def test_notify_coroutine_with_running_loop(self) -> None:
        state = AppState()
        called: list[bool] = []

        async def async_listener() -> None:
            called.append(True)

        state.subscribe(async_listener)
        state.notify()
        await asyncio.sleep(0.01)
        assert called == [True]

    def test_command_palette_toggle_and_set(self) -> None:
        state = AppState()
        assert state.command_palette_open is False
        state.set_command_palette_open(True)
        assert state.command_palette_open is True
        state.toggle_command_palette()
        assert state.command_palette_open is False


class TestMvgeStatus:
    def test_default_status_is_idle(self) -> None:
        state = AppState()
        assert state.mvge_status == "idle"

    def test_set_mvge_status_updates_field(self) -> None:
        state = AppState()
        state.set_mvge_status("channeling")
        assert state.mvge_status == "channeling"
        state.set_mvge_status("working")
        assert state.mvge_status == "working"

    def test_set_mvge_status_notifies_listeners(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.set_mvge_status("channeling")
        assert called == [True]


def test_notify_does_not_call_private_fire() -> None:
    """Verify notify does not invoke private _fire to prevent duplicate refreshes
    and unawaited coroutines."""
    state = AppState()

    fired = False

    class FakeAwaitableResponse:
        async def _fire(self) -> None:
            nonlocal fired
            fired = True

    fake = FakeAwaitableResponse()

    def listener() -> FakeAwaitableResponse:
        return fake

    state.subscribe(listener)
    state.notify()
    assert fired is False


class TestLoadMessagesForTome:
    def test_notifies_listeners_after_loading(self, tmp_path: Path) -> None:
        """load_messages_for_tome must notify subscribers after loading entries."""
        state, tome_dir = _make_state_with_tomes(str(tmp_path))
        tome_id = _create_tome(tome_dir, str(tmp_path))
        _append_message(tome_dir, tome_id, "user", "Hello", "m1")
        _append_message(tome_dir, tome_id, "assistant", "Hi there", "m2")

        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.load_messages_for_tome(tome_id)

        assert called == [True]
        assert len(state.messages) == 2


class TestCardExpansion:
    """Verify card expansion state tracking in AppState."""

    def test_default_expansion(self) -> None:
        state = AppState()
        assert state.is_card_expanded("card_1", default=False) is False
        assert state.is_card_expanded("card_1", default=True) is True

    def test_set_card_expanded(self) -> None:
        state = AppState()
        state.set_card_expansion("thought_0_0", True)
        assert state.is_card_expanded("thought_0_0", default=False) is True
        assert state.is_card_expanded("thought_0_0", default=True) is True

    def test_set_card_collapsed(self) -> None:
        state = AppState()
        state.set_card_expansion("thought_0_0", True)
        state.set_card_expansion("thought_0_0", False)
        assert state.is_card_expanded("thought_0_0", default=True) is False

    def test_set_card_expansion_does_not_notify(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.set_card_expansion("step_1_0", True)
        assert called == []


class TestStreamingListeners:
    """Verify isolated streaming listener registration and dispatch."""

    def test_streaming_listener_isolation(self) -> None:
        state = AppState()
        general_notified: list[int] = []
        streaming_notified: list[int] = []

        state.subscribe(lambda: general_notified.append(1))
        state.subscribe_streaming(lambda: streaming_notified.append(1))

        # Rapid streaming notification only notifies streaming listener
        state.notify_streaming()
        assert streaming_notified == [1]
        assert general_notified == []

        # Full notify triggers only general listeners
        state.notify()
        assert general_notified == [1]
        assert streaming_notified == [1]

    def test_streaming_fallback_when_no_streaming_listeners(self) -> None:
        state = AppState()
        general_notified: list[int] = []
        state.subscribe(lambda: general_notified.append(1))

        # Falls back to general listener when no streaming listeners registered
        state.notify_streaming()
        assert general_notified == [1]

    def test_unsubscribe_streaming(self) -> None:
        state = AppState()
        notified: list[int] = []

        def cb() -> None:
            notified.append(1)

        state.subscribe_streaming(cb)
        state.notify_streaming()
        assert notified == [1]

        state.unsubscribe_streaming(cb)
        state.notify_streaming()
        assert notified == [1]


class TestViewListeners:
    def test_subscribe_view_registers_globally(self) -> None:
        state = AppState()
        notified: list[int] = []
        state.subscribe_view("panel", lambda: notified.append(1))
        state.notify()
        assert notified == [1]
        assert state.view_listener_count("panel") == 1
        assert state.view_listener_count() == 1

    def test_subscribe_view_dedupes(self) -> None:
        state = AppState()

        def cb() -> None:
            pass

        state.subscribe_view("panel", cb)
        state.subscribe_view("panel", cb)
        assert state.view_listener_count("panel") == 1

    def test_subscribe_streaming_view_targets_streaming(self) -> None:
        state = AppState()
        notified: list[int] = []
        state.subscribe_streaming_view("bubble", lambda: notified.append(1))
        state.notify_streaming()
        assert notified == [1]
        assert state.view_listener_count("bubble") == 1

    def test_clear_view_listeners_detaches_key(self) -> None:
        state = AppState()
        notified: list[int] = []
        state.subscribe_view("panel", lambda: notified.append(1))
        state.subscribe_view("other", lambda: notified.append(1))
        state.clear_view_listeners("panel")
        state.notify()
        assert notified == [1]
        assert state.view_listener_count("panel") == 0
        assert state.view_listener_count() == 1

    def test_clear_view_listeners_missing_key_is_noop(self) -> None:
        state = AppState()
        state.clear_view_listeners("absent")
        assert state.view_listener_count() == 0

    def test_clear_all_view_listeners(self) -> None:
        state = AppState()
        state.subscribe_view("a", lambda: None)
        state.subscribe_streaming_view("b", lambda: None)
        state.clear_all_view_listeners()
        assert state.view_listener_count() == 0
        notified: list[int] = []
        state.subscribe(lambda: notified.append(1))
        state.notify()
        assert notified == [1]


class TestCascadingSelectorState:
    def test_default_cascading_state(self) -> None:
        state = AppState()
        assert state.selected_realm == "openrouter"
        assert state.selected_provider == "nvidia"
        assert state.selected_model == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert state.contemplation_level == "medium"
        assert state.is_router_realm() is True

    def test_get_realms(self) -> None:
        state = AppState()
        realms = state.get_realms()
        assert "openrouter" in realms

    def test_get_providers_for_router_and_direct(self) -> None:
        state = AppState()
        providers = state.get_providers_for_selected_realm()
        assert isinstance(providers, list)
        assert len(providers) > 0
        assert "nvidia" in providers

        # Direct realm has no providers
        with patch.object(state, "is_router_realm", return_value=False):
            assert state.get_providers_for_selected_realm() == []

    def test_switch_realm_to_direct_clears_provider(self) -> None:
        state = AppState()
        with patch("mvgeos_gui.state.is_realm_router", return_value=False):
            state.switch_realm("ollama")
            assert state.selected_realm == "ollama"
            assert state.selected_provider is None

    def test_switch_provider_cascades_model(self) -> None:
        state = AppState()
        state.switch_provider("anthropic")
        assert state.selected_provider == "anthropic"

    def test_switch_model_syncs_provider_prefix(self) -> None:
        state = AppState()
        state.switch_model("anthropic/claude-3-5-sonnet")
        assert state.selected_model == "anthropic/claude-3-5-sonnet"
        assert state.selected_provider == "anthropic"

    def test_set_contemplation_level(self) -> None:
        state = AppState()
        called: list[bool] = []
        state.subscribe(lambda: called.append(True))
        state.set_contemplation_level("x-high")
        assert state.contemplation_level == "x-high"
        assert called == [True]

    def test_supports_contemplation_and_levels(self) -> None:
        state = AppState()
        levels = state.get_contemplation_levels_for_selected_model()
        assert isinstance(levels, list)
        assert state.supports_contemplation_for_selected_model() is True

    def test_get_model_options_for_selection_router_strips_provider_prefix(
        self,
    ) -> None:
        state = AppState()
        options = state.get_model_options_for_selection()
        assert "nvidia/nemotron-3-ultra-550b-a55b:free" in options
        assert (
            options["nvidia/nemotron-3-ultra-550b-a55b:free"]
            == "Nemotron 3 Ultra (free)"
        )

    def test_get_model_options_for_selection_direct_preserves_names(self) -> None:
        state = AppState()
        mock_models = {"direct/model-1": "Direct: Model 1"}
        with (
            patch.object(state, "is_router_realm", return_value=False),
            patch("mvgeos_gui.state.get_model_options", return_value=mock_models),
            patch.object(
                state, "get_models_for_selection", return_value=["direct/model-1"]
            ),
        ):
            options = state.get_model_options_for_selection()
            assert options["direct/model-1"] == "Direct: Model 1"


class TestRuneManagementState:
    """Unit tests for rune marketplace and extension management in AppState."""

    def test_is_rune_installed(self, tmp_path: Path) -> None:
        state = AppState()
        target_dir = tmp_path / "test-rune"
        target_dir.mkdir()
        with patch("pathlib.Path.expanduser", return_value=tmp_path):
            assert state.is_rune_installed("test-rune") is True
            assert state.is_rune_installed("missing-rune") is False

    @pytest.mark.asyncio
    async def test_fetch_marketplace_runes_async(self) -> None:
        state = AppState()
        mock_catalog = {"openrouter-realm": {"version": "0.1.0"}}
        with patch(
            "mvgeos_gui.state.fetch_marketplace_runes", return_value=mock_catalog
        ):
            result = await state.fetch_marketplace_runes_async()
            assert result == mock_catalog

    @pytest.mark.asyncio
    async def test_list_installed_runes_async(self) -> None:
        state = AppState()
        mock_installed = [{"name": "test-rune", "version": "1.0.0"}]
        with patch(
            "mvgeos_gui.state.list_installed_runes", return_value=mock_installed
        ):
            result = await state.list_installed_runes_async()
            assert result == mock_installed

    @pytest.mark.asyncio
    async def test_install_rune_async_success(self) -> None:
        state = AppState()
        notified: list[bool] = []
        state.subscribe(lambda: notified.append(True))
        mock_agent = MagicMock()
        mock_agent._load_runes = AsyncMock()
        state.agent_service = MagicMock()
        state.agent_service._agent = mock_agent

        with patch(
            "mvgeos_gui.state.install_rune", return_value=Path("/tmp/installed")
        ):
            result = await state.install_rune_async("my-rune")
            assert result is True
            assert len(notified) > 0
            mock_agent._load_runes.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_install_rune_async_failure(self) -> None:
        state = AppState()
        with patch("mvgeos_gui.state.install_rune", side_effect=RuntimeError("fail")):
            result = await state.install_rune_async("bad-rune")
            assert result is False

    @pytest.mark.asyncio
    async def test_uninstall_rune_async(self) -> None:
        state = AppState()
        notified: list[bool] = []
        state.subscribe(lambda: notified.append(True))

        with (
            patch(
                "mvgeos_gui.state.uninstall_rune", return_value=True
            ) as mock_uninstall,
            patch("mvgeos_gui.state.get_default_realm_registry") as mock_registry_fn,
        ):
            mock_registry = MagicMock()
            mock_registry_fn.return_value = mock_registry
            result = await state.uninstall_rune_async("my-rune")
            assert result is True
            mock_uninstall.assert_called_once_with("my-rune")
            mock_registry.unregister_realm_factory.assert_called_once_with("my-rune")
            assert len(notified) > 0

    def test_is_mvge_installed(self, tmp_path: Path) -> None:
        state = AppState()
        with patch("pathlib.Path.expanduser", return_value=tmp_path):
            agent_dir = tmp_path / "my_mvge"
            assert state.is_mvge_installed("my_mvge") is False
            agent_dir.mkdir(parents=True)
            assert state.is_mvge_installed("my-mvge") is True

    @pytest.mark.asyncio
    async def test_fetch_marketplace_mvges_async(self) -> None:
        state = AppState()
        mock_data = {"test": {"name": "test"}}
        with patch("mvgeos_gui.state.fetch_marketplace_mvges", return_value=mock_data):
            result = await state.fetch_marketplace_mvges_async()
            assert result == mock_data

    @pytest.mark.asyncio
    async def test_list_installed_mvges_async(self) -> None:
        state = AppState()
        mock_installed = [{"name": "test"}]
        with patch(
            "mvgeos_gui.state.list_installed_mvges", return_value=mock_installed
        ):
            result = await state.list_installed_mvges_async()
            assert result == mock_installed

    @pytest.mark.asyncio
    async def test_install_mvge_async_success(self) -> None:
        state = AppState()
        notified: list[bool] = []
        state.subscribe(lambda: notified.append(True))
        with patch(
            "mvgeos_gui.state.install_mvge", return_value=Path("/tmp/installed")
        ):
            result = await state.install_mvge_async("my-mvge")
            assert result is True
            assert len(notified) > 0

    @pytest.mark.asyncio
    async def test_install_mvge_async_failure(self) -> None:
        state = AppState()
        with patch("mvgeos_gui.state.install_mvge", side_effect=RuntimeError("fail")):
            result = await state.install_mvge_async("bad-mvge")
            assert result is False

    @pytest.mark.asyncio
    async def test_uninstall_mvge_async_success(self) -> None:
        state = AppState()
        notified: list[bool] = []
        state.subscribe(lambda: notified.append(True))
        with patch(
            "mvgeos_gui.state.uninstall_mvge", return_value=True
        ) as mock_uninstall:
            result = await state.uninstall_mvge_async("my-mvge")
            assert result is True
            mock_uninstall.assert_called_once_with("my-mvge")
            assert len(notified) > 0

    @pytest.mark.asyncio
    async def test_uninstall_mvge_async_failure(self) -> None:
        state = AppState()
        with patch("mvgeos_gui.state.uninstall_mvge", side_effect=RuntimeError("fail")):
            result = await state.uninstall_mvge_async("bad-mvge")
            assert result is False
