"""Main chat panel: toolbar, message list, and side panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from mvgeos_gui.components.composer import (
    _scroll_to_bottom,
    fill_composer,
    render_composer,
)
from mvgeos_gui.components.diff_viewer import render_diff_viewer
from mvgeos_gui.components.file_tree import render_file_tree
from mvgeos_gui.components.message_parts import render_assistant_message
from mvgeos_gui.state import AppState

EXAMPLE_PROMPTS = [
    "Explain this project structure",
    "Find all TODO comments",
    "Run the test suite",
    "Help me debug an error",
]


def render_chat_panel(state: AppState) -> ui.column:
    """Render the main chat panel with toolbar, messages, side panel, and composer."""
    # Drop the previous render pass's view listeners first: this render
    # replaces those elements, and stale refreshables would otherwise keep
    # firing against deleted elements on every state notification.
    state.clear_all_view_listeners()
    container = ui.column().classes(
        "flex-1 w-full h-full flex flex-col overflow-hidden"
    )

    with container:
        # Toolbar
        @ui.refreshable
        def toolbar_view() -> None:
            with (
                ui.row().classes(
                    "w-full h-11 items-center justify-between px-3 "
                    "border-b border-[#292335] shrink-0"
                ),
                ui.row().classes("items-center gap-1"),
            ):
                if state.project_path:
                    with ui.row().classes(
                        "items-center gap-1.5 mr-2 px-2 py-0.5 rounded bg-[#0e0e12]/60"
                    ):
                        ui.icon("folder_open", size="12px").classes("text-[#9c94b3]")
                        ui.label(
                            state.project_path.name or str(state.project_path)
                        ).classes("text-xs text-[#9c94b3] max-w-[300px] truncate")

                _toolbar_button(
                    icon="shield",
                    title="Review panel",
                    active=state.review_open,
                    on_click=state.toggle_review,
                )

                # Right toolbar actions
                with ui.row().classes("items-center gap-1 ml-auto"):

                    def _on_plan_mode_click() -> None:
                        active_spells = state.toggle_plan_mode()
                        if state.plan_mode and not active_spells:
                            ui.notify(
                                "Plan mode is on, but no spells are marked read-only.",
                                type="warning",
                            )

                    _toolbar_button(
                        icon="search",
                        title="Command palette (Ctrl+Shift+P)",
                        on_click=lambda: state.set_command_palette_open(True),
                    )
                    _toolbar_button(
                        icon="edit_off",
                        title="Plan mode: read-only spells only",
                        active=state.plan_mode,
                        on_click=_on_plan_mode_click,
                        marker="chat_toolbar_plan_mode_btn",
                    )
                    _toolbar_button(
                        icon="folder_open",
                        title="Browse files",
                        active=state.chat_side_panel == "files",
                        on_click=lambda: state.set_chat_side_panel(
                            None if state.chat_side_panel == "files" else "files"
                        ),
                    )
                    _toolbar_button(
                        icon="difference",
                        title="View changes",
                        active=state.chat_side_panel == "diff",
                        on_click=lambda: state.set_chat_side_panel(
                            None if state.chat_side_panel == "diff" else "diff"
                        ),
                    )
                    _toolbar_button(
                        icon="tune",
                        title="Settings",
                        on_click=state.open_app_settings,
                        marker="chat_toolbar_settings_btn",
                    )

        toolbar_view()

        last_toolbar_state = [
            (
                state.review_open,
                state.chat_side_panel,
                state.plan_mode,
                str(state.project_path),
            )
        ]

        def _on_toolbar_check() -> None:
            cur = (
                state.review_open,
                state.chat_side_panel,
                state.plan_mode,
                str(state.project_path),
            )
            if cur != last_toolbar_state[0]:
                last_toolbar_state[0] = cur
                toolbar_view.refresh()

        state.subscribe_view("chat_panel_toolbar", _on_toolbar_check)

        # Body: messages + side panel
        with ui.row().classes("flex-1 w-full overflow-hidden"):
            # Main chat column
            with ui.column().classes(
                "flex-1 h-full flex flex-col overflow-hidden relative"
            ):
                # Scrollable messages area
                with (
                    ui.column()
                    .classes("flex-1 w-full overflow-y-auto")
                    .props('id="chat-messages-area"')
                ) as messages_area:

                    @ui.refreshable
                    def static_messages_view() -> None:
                        if not state.messages:
                            return
                        with ui.column().classes("w-full space-y-4"):
                            msgs_to_render = (
                                state.messages[:-1]
                                if state.is_channeling
                                else state.messages
                            )
                            for idx, msg in enumerate(msgs_to_render):
                                if msg.role == "user":
                                    _render_user_message(msg)
                                else:
                                    render_assistant_message(msg, idx, state)
                            _scroll_to_bottom(messages_area.id, force=False)

                    @ui.refreshable
                    def streaming_bubble_view() -> None:
                        if state.messages and state.is_channeling:
                            last_idx = len(state.messages) - 1
                            render_assistant_message(
                                state.messages[last_idx], last_idx, state
                            )
                            _scroll_to_bottom(messages_area.id, force=False)

                    @ui.refreshable
                    def empty_state_view() -> None:
                        if state.messages:
                            return
                        with (
                            ui.column()
                            .classes(
                                "w-full min-h-full items-center justify-center "
                                "px-4 py-8"
                            )
                            .mark("empty-state")
                        ):
                            _render_empty_hero(state)
                            with ui.column().classes("w-full max-w-3xl mt-2"):
                                render_composer(state)

                    static_messages_view()
                    empty_state_view()
                    streaming_bubble_view()

                # Floating scroll-to-bottom button
                with (
                    ui.button(
                        icon="keyboard_arrow_down",
                        on_click=lambda: _scroll_to_bottom(
                            messages_area.id, force=True
                        ),
                    )
                    .props('round unelevated size=sm id="chat-scroll-bottom-btn"')
                    .classes(
                        "absolute right-4 bottom-4 z-30 bg-[#0e0e12] "
                        "hover:bg-[#292335] text-[#eceaf4] border border-[#292335] "
                        "hover:border-[#7b6cf6] shadow-xl transition-all "
                        "duration-200 opacity-0 pointer-events-none"
                    )
                    .mark("chat-scroll-bottom-btn")
                ):
                    ui.tooltip("Scroll to bottom")

                # Subscribe to state changes to refresh views
                state.subscribe_view(
                    "chat_panel_messages", static_messages_view.refresh
                )
                state.subscribe_view(
                    "chat_panel_messages", streaming_bubble_view.refresh
                )
                state.subscribe_streaming_view(
                    "chat_panel_messages", streaming_bubble_view.refresh
                )

                # Composer dock: exactly one composer instance lives here while
                # the chat has messages; the empty state hosts it otherwise.
                @ui.refreshable
                def bottom_composer_view() -> None:
                    if state.messages:
                        render_composer(state)

                bottom_composer_view()

                # Move the single composer between the centered empty-state
                # slot and the bottom dock when the chat gains or loses
                # messages. The guard keeps every other notification from
                # re-rendering (and wiping) the textarea.
                last_had_messages = [bool(state.messages)]

                def _on_composer_placement_check() -> None:
                    cur = bool(state.messages)
                    if cur == last_had_messages[0]:
                        return
                    last_had_messages[0] = cur
                    for key in (
                        "composer_chips",
                        "composer_prompt",
                        "composer_actions",
                        "cascading_selector",
                        "empty_state_status",
                    ):
                        state.clear_view_listeners(key)
                    state.get_autocomplete_service().clear_items_changed_listeners()
                    empty_state_view.refresh()
                    bottom_composer_view.refresh()

                state.subscribe_view("composer_placement", _on_composer_placement_check)

            # Side panel
            @ui.refreshable
            def side_panel_view() -> None:
                if state.chat_side_panel in ("files", "diff"):
                    with ui.column().classes(
                        "w-80 border-l border-[#292335] bg-[#08080a] "
                        "shrink-0 overflow-hidden"
                    ):
                        with ui.row().classes(
                            "w-full h-11 items-center justify-between px-3 "
                            "border-b border-[#292335]"
                        ):
                            ui.label(
                                "Files" if state.chat_side_panel == "files" else "Diff"
                            ).classes("text-xs font-semibold text-[#eceaf4]")
                            ui.button(
                                icon="close",
                                on_click=lambda: state.set_chat_side_panel(None),
                            ).props("flat dense round text-color=grey-5 size=xs")
                        if state.chat_side_panel == "files":
                            render_file_tree(state)
                        else:
                            render_diff_viewer(state)

            side_panel_view()

            last_side_panel_state = [state.chat_side_panel]

            def _on_side_panel_check() -> None:
                if state.chat_side_panel != last_side_panel_state[0]:
                    last_side_panel_state[0] = state.chat_side_panel
                    side_panel_view.refresh()

            state.subscribe_view("chat_side_panel", _on_side_panel_check)

    return container


def _render_empty_hero(state: AppState) -> None:
    """Render the empty-chat hero: icon, title, live status, prompt chips.

    Layout is owned by the caller (empty_state_view centers this together
    with the composer); this renders the hero content only.
    """
    with ui.row().classes(
        "w-14 h-14 rounded-2xl bg-[#0e0e12] border border-[#292335] "
        "items-center justify-center shadow-lg mb-6"
    ):
        ui.icon("auto_awesome", size="28px").classes("text-[#7b6cf6]")

    ui.label("What should Mvge work on?").classes(
        "text-2xl font-semibold text-[#eceaf4] tracking-tight"
    )

    @ui.refreshable
    def empty_status_view() -> None:
        status_text = {
            "channeling": "Mvge is channeling a response…",
            "working": "Mvge is working…",
            "idle": "Choose a project — Mvge starts when you send.",
        }.get(state.mvge_status, "Choose a project — Mvge starts when you send.")
        ui.label(status_text).classes("text-sm text-[#9c94b3] mt-1 mb-8")

    empty_status_view()

    last_empty_status = [state.mvge_status]

    def _on_empty_status_check() -> None:
        if state.mvge_status != last_empty_status[0]:
            last_empty_status[0] = state.mvge_status
            empty_status_view.refresh()

    state.subscribe_view("empty_state_status", _on_empty_status_check)

    with ui.row().classes("gap-2 flex-wrap justify-center mb-6"):
        for prompt in EXAMPLE_PROMPTS:
            ui.button(
                prompt,
                on_click=lambda p=prompt: fill_composer(state, p),
            ).props("unelevated dense no-caps").classes(
                "rounded-lg border border-[#292335] px-3 py-1.5 text-xs "
                "text-[#9c94b3] hover:border-[#7b6cf6] hover:text-[#eceaf4] "
                "transition-colors"
            )


def _render_messages(state: AppState) -> None:
    """Render the message thread."""
    for idx, msg in enumerate(state.messages):
        if msg.role == "user":
            _render_user_message(msg)
        else:
            render_assistant_message(msg, idx, state)


def _render_user_message(msg: object) -> None:
    """Render a user message bubble."""
    content = getattr(msg, "content", "")
    timestamp = getattr(msg, "timestamp", "")
    with (
        ui.column().classes("w-full max-w-3xl mx-auto px-6 py-3 items-end"),
        ui.card().classes(
            "w-auto max-w-[85%] bg-[#0e0e12] border border-[#292335] "
            "rounded-2xl p-4 shadow-md"
        ),
    ):
        with ui.row().classes(
            "w-full items-center justify-between pb-1 border-b border-[#241f38] mb-2"
        ):
            with ui.row().classes("items-center gap-1.5"):
                ui.icon("account_circle", size="16px").classes("text-[#7b6cf6]")
                ui.label("Summoner").classes("text-xs font-semibold text-[#eceaf4]")
            if timestamp:
                ui.label(timestamp).classes("text-[10px] text-[#6e6584] font-mono")
        ui.label(content).classes(
            "text-xs text-[#eceaf4] whitespace-pre-wrap leading-relaxed"
        )


def _toolbar_button(
    icon: str,
    title: str,
    active: bool = False,
    on_click: Callable[[], Any] | None = None,
    marker: str | None = None,
) -> None:
    """Render a toolbar icon button."""
    btn_cls = (
        "bg-card text-primary"
        if active
        else "text-dim hover:text-secondary hover:bg-highlight"
    )
    btn = (
        ui.button(icon=icon, on_click=on_click)
        .props("flat dense round size=xs")
        .classes(f"{btn_cls} p-0.5")
    )
    if marker:
        btn.mark(marker)
    with btn:
        ui.tooltip(title)
