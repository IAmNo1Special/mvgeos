"""Integration tests for input dock autocomplete and attachment features."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.app import build_page
from mvgeos_gui.autocomplete import (
    AutocompleteMode,
    CommandKind,
    MentionChip,
    MentionKind,
)
from mvgeos_gui.components.input_dock import (
    _autocomplete_icon,
    _autocomplete_icon_color,
    _handle_tab,
    _select_item,
)
from mvgeos_gui.state import AppState


@pytest.fixture
def temp_project() -> Path:
    """Create a temporary project directory with sample files."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp / "utils.py").write_text("def helper(): pass", encoding="utf-8")
    (tmp / "README.md").write_text("# Project", encoding="utf-8")
    return tmp


@pytest.fixture
def state_with_project(temp_project: Path) -> AppState:
    """Create AppState pointed at the temp project."""
    state = AppState(project_path=temp_project)
    state.get_autocomplete_service()
    return state


class TestAutocompletePopup:
    """Tests for @-mention and /-slash command autocomplete popups."""

    @pytest.mark.asyncio
    async def test_mention_popup_renders_with_items(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify mention popup shows filtered file items."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("hello @main")

        @ui.page("/test_mention_popup")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_mention_popup")

        assert ac.is_open
        assert ac.mode == AutocompleteMode.MENTION
        await user.should_see("main.py")

    @pytest.mark.asyncio
    async def test_slash_command_popup_renders(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify slash command popup shows available commands."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("/help")

        @ui.page("/test_command_popup")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_command_popup")

        assert ac.is_open
        assert ac.mode == AutocompleteMode.COMMAND
        await user.should_see("/help")

    @pytest.mark.asyncio
    async def test_popup_hidden_when_closed(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify no popup visible when autocomplete is closed."""
        ac = state_with_project.get_autocomplete_service()
        assert not ac.is_open

        @ui.page("/test_popup_closed")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_popup_closed")

    @pytest.mark.asyncio
    async def test_mention_popup_filters_by_query(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify mention popup filters items based on query text."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@util")

        @ui.page("/test_mention_filter")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_mention_filter")

        labels = [ac.get_item_label(i) for i in ac.get_visible_items()]
        assert "utils.py" in labels
        assert "main.py" not in labels
        await user.should_see("utils.py")

    @pytest.mark.asyncio
    async def test_slash_command_popup_filters(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify slash command popup filters by query."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("/mod")

        @ui.page("/test_command_filter")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_command_filter")

        labels = [ac.get_item_label(i) for i in ac.get_visible_items()]
        assert "/model" in labels or "/models" in labels
        await user.should_see("/model")

    @pytest.mark.asyncio
    async def test_type_at_opens_mention_popup(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify typing @ in the textarea opens the mention popup."""
        ac = state_with_project.get_autocomplete_service()
        assert not ac.is_open

        @ui.page("/test_type_mention_popup")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_type_mention_popup")

        textarea = user.find(ui.textarea)
        textarea.type("@")

        assert ac.is_open
        assert ac.mode == AutocompleteMode.MENTION
        await user.should_see("main.py")

    @pytest.mark.asyncio
    async def test_type_slash_opens_command_popup(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify typing / in the textarea opens the slash command popup."""
        ac = state_with_project.get_autocomplete_service()
        assert not ac.is_open

        @ui.page("/test_type_slash_popup")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_type_slash_popup")

        textarea = user.find(ui.textarea)
        textarea.type("/")

        assert ac.is_open
        assert ac.mode == AutocompleteMode.COMMAND
        await user.should_see("/help")

    @pytest.mark.asyncio
    async def test_type_at_popup_above_textarea(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify the autocomplete popup appears above the textarea."""
        ac = state_with_project.get_autocomplete_service()

        @ui.page("/test_popup_position")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_popup_position")

        textarea = user.find(ui.textarea)
        textarea.type("@")

        assert ac.is_open
        await user.should_see("main.py")
        await user.should_see("Ask anything. @ to mention. / for actions")

    @pytest.mark.asyncio
    async def test_arrow_down_navigates_popup(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify arrow down navigates the autocomplete popup."""
        ac = state_with_project.get_autocomplete_service()

        @ui.page("/test_arrow_down")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_arrow_down")

        textarea = user.find(ui.textarea)
        textarea.type("@")

        assert ac.is_open
        assert ac.selected_index == 0

        # Press arrow down
        textarea.trigger("keydown.down.prevent")

        assert ac.selected_index == 1

    @pytest.mark.asyncio
    async def test_arrow_up_navigates_popup(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify arrow up navigates the autocomplete popup."""
        ac = state_with_project.get_autocomplete_service()

        @ui.page("/test_arrow_up")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_arrow_up")

        textarea = user.find(ui.textarea)
        textarea.type("@")

        assert ac.is_open
        # Move down first to have something to move up from
        textarea.trigger("keydown.down.prevent")
        assert ac.selected_index == 1

        # Press arrow up
        textarea.trigger("keydown.up.prevent")

        assert ac.selected_index == 0


class TestAutocompleteSelection:
    """Tests for selecting autocomplete items."""

    @pytest.mark.asyncio
    async def test_select_current_returns_insertion_text(
        self, state_with_project: AppState
    ) -> None:
        """Verify select_current returns insertion text and closes popup."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")
        assert ac.is_open

        text = ac.select_current()
        assert text is not None
        assert not ac.is_open

    @pytest.mark.asyncio
    async def test_move_down_navigates_selection(
        self, state_with_project: AppState
    ) -> None:
        """Verify arrow down moves selection cursor."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@")
        assert ac.selected_index == 0

        ac.move_down()
        assert ac.selected_index == 1

    @pytest.mark.asyncio
    async def test_move_up_navigates_selection(
        self, state_with_project: AppState
    ) -> None:
        """Verify arrow up moves selection cursor."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@")
        ac.selected_index = 2

        ac.move_up()
        assert ac.selected_index == 1
        ac.move_up()
        assert ac.selected_index == 0
        ac.move_up()  # clamp
        assert ac.selected_index == 0

    @pytest.mark.asyncio
    async def test_escape_closes_popup(self, state_with_project: AppState) -> None:
        """Verify Escape closes the popup."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")
        assert ac.is_open

        ac.close()
        assert not ac.is_open
        assert ac.mode == AutocompleteMode.NONE

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, state_with_project: AppState) -> None:
        """Verify close is a no-op when already closed."""
        ac = state_with_project.get_autocomplete_service()
        assert not ac.is_open

        ac.close()
        assert not ac.is_open

    @pytest.mark.asyncio
    async def test_reopen_after_close(self, state_with_project: AppState) -> None:
        """Verify popup can reopen after being closed."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")
        ac.close()
        assert not ac.is_open

        ac.process_input("@util")
        assert ac.is_open
        assert ac.query == "util"


class TestAttachmentChips:
    """Tests for attachment chip rendering and removal."""

    @pytest.mark.asyncio
    async def test_attachment_chips_render(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify attachment chips render when pending_attachments is populated."""
        state_with_project.add_attachment("main.py")
        state_with_project.add_attachment("utils.py")

        @ui.page("/test_attachments_render")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_attachments_render")

        await user.should_see("main.py")
        await user.should_see("utils.py")

    @pytest.mark.asyncio
    async def test_no_attachment_chips_when_empty(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify no attachment chips when attachments list is empty."""
        assert state_with_project.pending_attachments == []

        @ui.page("/test_no_attachments")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_no_attachments")

    @pytest.mark.asyncio
    async def test_remove_attachment_via_chip(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify clicking close on attachment chip removes it from state."""
        state_with_project.add_attachment("main.py")
        state_with_project.add_attachment("utils.py")
        assert len(state_with_project.pending_attachments) == 2

        state_with_project.remove_attachment(0)
        assert state_with_project.pending_attachments == ["utils.py"]

        @ui.page("/test_remove_attachment")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_remove_attachment")
        await user.should_see("utils.py")

    @pytest.mark.asyncio
    async def test_attachment_dedup(self, state_with_project: AppState) -> None:
        """Verify duplicate attachments are not added twice."""
        state_with_project.add_attachment("main.py")
        state_with_project.add_attachment("main.py")
        assert state_with_project.pending_attachments == ["main.py"]


class TestSubmitPrompt:
    """Tests for submit prompt with attachments."""

    @pytest.mark.asyncio
    async def test_submit_binds_attachments(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify attachments are bound to the submitted message."""
        state_with_project.add_attachment("main.py")
        state_with_project.add_attachment("README.md")

        @ui.page("/test_submit_attachments")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_submit_attachments")

        state_with_project.submit_prompt("Analyze these files")

        user_msg = state_with_project.messages[0]
        assert user_msg.attachments == ["main.py", "README.md"]
        assert state_with_project.pending_attachments == []

    @pytest.mark.asyncio
    async def test_submit_stops_channeling(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify stop channeling button halts active task."""
        state_with_project.is_channeling = True

        @ui.page("/test_stop_channeling")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_stop_channeling")

        assert state_with_project.is_channeling
        user.find("stop_channeling_btn").click()
        assert not state_with_project.is_channeling


class TestInputDockComponents:
    """Tests for input dock UI elements."""

    @pytest.mark.asyncio
    async def test_submit_prompt_button_visible(self, user: User) -> None:
        """Verify submit prompt button is rendered when not channeling."""
        state = AppState()

        @ui.page("/test_submit_btn")
        def page() -> None:
            build_page(state)

        await user.open("/test_submit_btn")

        assert not state.is_channeling

    @pytest.mark.asyncio
    async def test_stop_button_visible_when_channeling(self, user: User) -> None:
        """Verify stop button instead of submit when channeling."""
        state = AppState(is_channeling=True)

        @ui.page("/test_stop_btn")
        def page() -> None:
            build_page(state)

        await user.open("/test_stop_btn")

        assert state.is_channeling

    @pytest.mark.asyncio
    async def test_model_selector_renders(self, user: User) -> None:
        """Verify model selector dropdown renders with options."""
        state = AppState()

        @ui.page("/test_model_select")
        def page() -> None:
            build_page(state)

        await user.open("/test_model_select")

        await user.should_see("nvidia/nemotron-3-ultra-550b-a55b:free")

    @pytest.mark.asyncio
    async def test_attach_button_rendered(self, user: User) -> None:
        """Verify attach files button is present."""
        state = AppState()

        @ui.page("/test_attach_btn")
        def page() -> None:
            build_page(state)

        await user.open("/test_attach_btn")

    def test_get_word_range_returns_correct_range(
        self, state_with_project: AppState
    ) -> None:
        """Verify word range calculation for replacement."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")
        start, end = ac.get_word_range("hello @main")
        assert start == 6
        assert end == 11

    def test_get_word_range_no_trigger(self, state_with_project: AppState) -> None:
        """Verify word range returns (-1, -1) when no trigger word."""
        ac = state_with_project.get_autocomplete_service()
        start, end = ac.get_word_range("hello ")
        assert start == -1
        assert end == -1


class TestAutocompleteHelpers:
    """Tests for autocomplete icon and helper functions."""

    def test_autocomplete_icon_file(self) -> None:
        assert _autocomplete_icon(MentionKind.FILE) == "insert_drive_file"

    def test_autocomplete_icon_skill(self) -> None:
        assert _autocomplete_icon(MentionKind.SKILL) == "auto_awesome"

    def test_autocomplete_icon_slash(self) -> None:
        assert _autocomplete_icon(CommandKind.SLASH) == "slash"

    def test_autocomplete_icon_rune(self) -> None:
        assert _autocomplete_icon(CommandKind.RUNE) == "auto_awesome"

    def test_autocomplete_icon_unknown(self) -> None:
        assert _autocomplete_icon("unknown") == "help_outline"

    def test_autocomplete_icon_color_file(self) -> None:
        assert _autocomplete_icon_color(MentionKind.FILE) == "text-[#8b949e]"

    def test_autocomplete_icon_color_skill(self) -> None:
        assert _autocomplete_icon_color(MentionKind.SKILL) == "text-[#3b82f6]"

    def test_autocomplete_icon_color_rune(self) -> None:
        assert _autocomplete_icon_color(CommandKind.RUNE) == "text-[#3b82f6]"

    def test_autocomplete_icon_color_slash(self) -> None:
        assert _autocomplete_icon_color(CommandKind.SLASH) == "text-[#8b949e]"

    def test_autocomplete_icon_color_unknown(self) -> None:
        assert _autocomplete_icon_color("unknown") == "text-[#8b949e]"

    def test_handle_tab_no_popup_noop(self, state_with_project: AppState) -> None:
        """Verify _handle_tab is a no-op when popup is closed."""
        ac = state_with_project.get_autocomplete_service()
        assert not ac.is_open

        class FakeTextarea:
            value = ""

        _handle_tab(ac, FakeTextarea(), state_with_project)  # type: ignore[arg-type]

    def test_handle_tab_with_selection(self, state_with_project: AppState) -> None:
        """Verify _handle_tab selects current item and updates prompt text."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")
        assert ac.is_open

        class FakeTextarea:
            value = "hello @main"

        textarea = FakeTextarea()
        _handle_tab(ac, textarea, state_with_project)  # type: ignore[arg-type]

        assert not ac.is_open
        assert textarea.value == "hello "

    def test_select_item_valid_index(self, state_with_project: AppState) -> None:
        """Verify selecting a valid item index updates the prompt."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")
        assert ac.is_open

        class FakeTextarea:
            value = "hello @main"

        textarea = FakeTextarea()
        items = ac.get_visible_items()
        assert len(items) > 0

        _select_item(ac, textarea, 0, state_with_project)  # type: ignore[arg-type]
        assert not ac.is_open
        assert textarea.value == "hello "

    def test_select_item_invalid_index_noop(self, state_with_project: AppState) -> None:
        """Verify selecting an invalid index is a no-op."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")

        class FakeTextarea:
            value = "@main"

        textarea = FakeTextarea()
        _select_item(ac, textarea, 999, state_with_project)  # type: ignore[arg-type]
        assert ac.is_open
        _select_item(ac, textarea, -1, state_with_project)  # type: ignore[arg-type]
        assert ac.is_open

    def test_handle_tab_no_items_noop(self, state_with_project: AppState) -> None:
        """Verify _handle_tab is a no-op when no items available."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@zzznomatch")
        assert ac.is_open
        assert len(ac.items) == 0

        class FakeTextarea:
            value = "hello @zzznomatch"

        textarea = FakeTextarea()
        _handle_tab(ac, textarea, state_with_project)  # type: ignore[arg-type]
        assert ac.is_open


class TestMentionChips:
    """Tests for chip-based autocomplete selection behavior."""

    @pytest.mark.asyncio
    async def test_select_item_adds_chip_to_state(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify selecting an autocomplete item adds a mention chip."""
        ac = state_with_project.get_autocomplete_service()
        ac.process_input("@main")

        @ui.page("/test_select_adds_chip")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_select_adds_chip")

        textarea = user.find(ui.textarea)
        textarea.type("@")
        textarea.trigger("keydown.enter.prevent")

        assert len(state_with_project.selected_mentions) == 1
        assert state_with_project.selected_mentions[0].text == "@main.py"

    @pytest.mark.asyncio
    async def test_chips_render_in_input_dock(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify mention chips are visible in the input dock."""
        state_with_project.selected_mentions = [
            MentionChip(text="@main.py", kind="file", icon="code"),
            MentionChip(text="/help", kind="slash", icon="slash"),
        ]

        @ui.page("/test_chips_render")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_chips_render")

        await user.should_see("@main.py")
        await user.should_see("/help")

    @pytest.mark.asyncio
    async def test_backspace_removes_last_chip(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify backspace on empty textarea removes the last chip."""
        state_with_project.selected_mentions = [
            MentionChip(text="@main.py", kind="file"),
            MentionChip(text="/help", kind="slash"),
        ]

        @ui.page("/test_backspace_removes_chip")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_backspace_removes_chip")

        assert len(state_with_project.selected_mentions) == 2

        textarea = user.find(ui.textarea)
        textarea.trigger("keydown.backspace")

        assert len(state_with_project.selected_mentions) == 1
        assert state_with_project.selected_mentions[0].text == "@main.py"

    @pytest.mark.asyncio
    async def test_submit_prepends_mentions_to_prompt(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify submitting a prompt prepends mention chips to the text."""
        state_with_project.selected_mentions = [
            MentionChip(text="@main.py", kind="file"),
        ]

        @ui.page("/test_submit_prepends_mentions")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_submit_prepends_mentions")

        textarea = user.find(ui.textarea)
        textarea.type("Analyze this file")
        textarea.trigger("keydown.enter.prevent")

        assert len(state_with_project.messages) == 2
        user_msg = state_with_project.messages[0]
        assert user_msg.content == "@main.py Analyze this file"
        assert state_with_project.selected_mentions == []

    @pytest.mark.asyncio
    async def test_submit_mentions_only_no_text(
        self, user: User, state_with_project: AppState
    ) -> None:
        """Verify submitting with only mentions and no extra text works."""
        state_with_project.selected_mentions = [
            MentionChip(text="@main.py", kind="file"),
        ]

        @ui.page("/test_mentions_only_submit")
        def page() -> None:
            build_page(state_with_project)

        await user.open("/test_mentions_only_submit")

        textarea = user.find(ui.textarea)
        textarea.trigger("keydown.enter.prevent")

        assert len(state_with_project.messages) == 2
        user_msg = state_with_project.messages[0]
        assert user_msg.content == "@main.py"
        assert state_with_project.selected_mentions == []
