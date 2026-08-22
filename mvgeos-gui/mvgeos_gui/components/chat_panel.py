"""Main chat panel: toolbar, message list, side panel, and composer."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from nicegui import ui

from mvgeos_gui.autocomplete import AutocompleteService
from mvgeos_gui.components.message_parts import (
    render_assistant_message,
    render_streaming_bubble,
)
from mvgeos_gui.components.terminal_panel import render_terminal_panel
from mvgeos_gui.model_catalog import get_model_options
from mvgeos_gui.state import AppState
from mvgeos_gui.utils import copy_to_clipboard

EXAMPLE_PROMPTS = [
    "Explain this project structure",
    "Find all TODO comments",
    "Run the test suite",
    "Help me debug an error",
]


def render_chat_panel(state: AppState) -> ui.column:
    """Render the main chat panel with toolbar, messages, side panel, and composer."""
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
                    "border-b border-[#2b2f3d] shrink-0"
                ),
                ui.row().classes("items-center gap-1"),
            ):
                if state.project_path:
                    with ui.row().classes(
                        "items-center gap-1.5 mr-2 px-2 py-0.5 rounded bg-[#1e212b]/60"
                    ):
                        ui.icon("folder_open", size="12px").classes("text-[#8b949e]")
                        ui.label(
                            state.project_path.name or str(state.project_path)
                        ).classes("text-xs text-[#8b949e] max-w-[300px] truncate")

                _toolbar_button(
                    icon="panel_left_close" if state.sidebar_open else "panel_left",
                    title="Toggle sidebar",
                    on_click=state.toggle_sidebar,
                )
                _toolbar_button(
                    icon="shield",
                    title="Review panel",
                    active=state.review_open,
                    on_click=state.toggle_review,
                )
                _toolbar_button(
                    icon="terminal",
                    title="Terminal",
                    active=state.terminal_open,
                    on_click=state.toggle_terminal,
                )

                # Right toolbar actions
                with ui.row().classes("items-center gap-1 ml-auto"):
                    _toolbar_button(
                        icon="search",
                        title="Command palette (Ctrl+K)",
                        on_click=lambda: state.set_command_palette_open(True),
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
                        on_click=lambda: state.set_current_view("settings"),
                    )

        toolbar_view()

        last_toolbar_state = [
            (
                state.sidebar_open,
                state.review_open,
                state.terminal_open,
                state.chat_side_panel,
                str(state.project_path),
            )
        ]

        def _on_toolbar_check() -> None:
            cur = (
                state.sidebar_open,
                state.review_open,
                state.terminal_open,
                state.chat_side_panel,
                str(state.project_path),
            )
            if cur != last_toolbar_state[0]:
                last_toolbar_state[0] = cur
                toolbar_view.refresh()

        state.subscribe(_on_toolbar_check)

        # Body: messages + side panel
        with ui.row().classes("flex-1 w-full overflow-hidden"):
            # Main chat column
            with ui.column().classes(
                "flex-1 h-full flex flex-col overflow-hidden relative"
            ):
                # Scrollable messages area
                with (
                    ui.column()
                    .classes("flex-1 w-full overflow-y-auto space-y-4")
                    .props('id="chat-messages-area"')
                ) as messages_area:

                    @ui.refreshable
                    def messages_view() -> None:
                        if not state.messages and not state.is_streaming:
                            _render_empty_chat(state)
                        else:
                            _render_messages(state)
                            _scroll_to_bottom(messages_area.id, force=False)

                    messages_view()

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
                        "absolute right-4 bottom-4 z-30 bg-[#1e212b] "
                        "hover:bg-[#2b2f3d] text-[#e6edf3] border border-[#2b2f3d] "
                        "hover:border-[#3b82f6] shadow-xl transition-all "
                        "duration-200 opacity-0 pointer-events-none"
                    )
                    .mark("chat-scroll-bottom-btn")
                ):
                    ui.tooltip("Scroll to bottom")

                # Subscribe to state changes to refresh just the messages area
                state.subscribe(messages_view.refresh)

                # Composer
                _render_composer(state)

                # Terminal overlay
                render_terminal_panel(state)

            # Side panel
            @ui.refreshable
            def side_panel_view() -> None:
                if state.chat_side_panel in ("files", "diff"):
                    with ui.column().classes(
                        "w-80 border-l border-[#2b2f3d] bg-[#13151b] "
                        "shrink-0 overflow-hidden"
                    ):
                        with ui.row().classes(
                            "w-full h-11 items-center justify-between px-3 "
                            "border-b border-[#2b2f3d]"
                        ):
                            ui.label(
                                "Files" if state.chat_side_panel == "files" else "Diff"
                            ).classes("text-xs font-semibold text-[#e6edf3]")
                            ui.button(
                                icon="close",
                                on_click=lambda: state.set_chat_side_panel(None),
                            ).props("flat dense round text-color=grey-5 size=xs")
                        if state.chat_side_panel == "files":
                            from mvgeos_gui.components.file_tree import (
                                render_file_tree,
                            )

                            render_file_tree(state)
                        else:
                            from mvgeos_gui.components.diff_viewer import (
                                render_diff_viewer,
                            )

                            render_diff_viewer(state)

            side_panel_view()

            last_side_panel_state = [state.chat_side_panel]

            def _on_side_panel_check() -> None:
                if state.chat_side_panel != last_side_panel_state[0]:
                    last_side_panel_state[0] = state.chat_side_panel
                    side_panel_view.refresh()

            state.subscribe(_on_side_panel_check)

    return container


def _render_empty_chat(state: AppState) -> None:
    """Render the centered empty-chat prompt."""
    with ui.column().classes("w-full h-full items-center justify-center px-4"):
        with ui.row().classes(
            "w-14 h-14 rounded-2xl bg-[#1e212b] border border-[#2b2f3d] "
            "items-center justify-center shadow-lg mb-6"
        ):
            ui.icon("auto_awesome", size="28px").classes("text-[#3b82f6]")

        ui.label("What should Mvge work on?").classes(
            "text-2xl font-semibold text-[#e6edf3] tracking-tight"
        )
        status_text = {
            "running": "Pick a project and describe what you want done.",
            "starting": "Starting Mvge agent…",
            "error": "Failed to start Mvge. Check settings.",
            "idle": "Choose a project — Mvge starts when you send.",
        }.get(state.pi_status, "Choose a project — Mvge starts when you send.")
        ui.label(status_text).classes("text-sm text-[#8b949e] mt-1 mb-8")

        with ui.row().classes("gap-2 flex-wrap justify-center mb-6"):
            for prompt in EXAMPLE_PROMPTS:
                ui.button(
                    prompt,
                    on_click=lambda p=prompt: _fill_composer(state, p),
                ).props("unelevated dense no-caps").classes(
                    "rounded-lg border border-[#2b2f3d] px-3 py-1.5 text-xs "
                    "text-[#8b949e] hover:border-[#3b82f6] hover:text-[#e6edf3] "
                    "transition-colors"
                )


def _render_messages(state: AppState) -> None:
    """Render the message thread."""
    for idx, msg in enumerate(state.messages):
        if msg.role == "user":
            _render_user_message(msg)
        else:
            render_assistant_message(msg, idx, state)

    if state.is_streaming:
        render_streaming_bubble(state)


def _render_user_message(msg: object) -> None:
    """Render a user message bubble."""
    content = getattr(msg, "content", "")
    timestamp = getattr(msg, "timestamp", "")
    with (
        ui.column().classes("w-full max-w-3xl mx-auto px-6 py-3 items-end"),
        ui.card().classes(
            "w-auto max-w-[85%] bg-[#1e212b] border border-[#2b2f3d] "
            "rounded-2xl p-4 shadow-md"
        ),
    ):
        with ui.row().classes(
            "w-full items-center justify-between pb-1 border-b border-[#252836] mb-2"
        ):
            with ui.row().classes("items-center gap-1.5"):
                ui.icon("account_circle", size="16px").classes("text-[#3b82f6]")
                ui.label("Summoner").classes("text-xs font-semibold text-[#e6edf3]")
            if timestamp:
                ui.label(timestamp).classes("text-[10px] text-[#64748b] font-mono")
        ui.label(content).classes(
            "text-xs text-[#e6edf3] whitespace-pre-wrap leading-relaxed"
        )


def _render_composer(state: AppState) -> None:
    """Render the bottom composer input area."""
    ac_service = state.get_autocomplete_service()

    with (
        ui.column().classes("w-full px-6 pb-6 pt-2 shrink-0"),
        ui.card().classes(
            "w-full bg-[#1e212b] border border-[#2b2f3d] rounded-2xl p-3 shadow-2xl"
        ),
    ):
        # Attachment and Mention chips
        @ui.refreshable
        def chips_view() -> None:
            if state.pending_attachments:
                with ui.row().classes("items-center gap-1.5 flex-wrap mb-2"):
                    for idx, name in enumerate(state.pending_attachments):
                        with ui.row().classes(
                            "items-center gap-1 px-2 py-0.5 rounded-md bg-[#2b2f3d]"
                        ):
                            ui.icon("insert_drive_file", size="12px").classes(
                                "text-[#8b949e]"
                            )
                            ui.label(name).classes(
                                "text-xs text-[#e6edf3] truncate max-w-[140px]"
                            )
                            ui.icon("close", size="10px").classes(
                                "text-[#64748b] cursor-pointer"
                            ).on("click", lambda _, i=idx: state.remove_attachment(i))

            if state.selected_mentions:
                with ui.row().classes("items-center gap-1.5 flex-wrap mb-2"):
                    for idx, chip in enumerate(state.selected_mentions):
                        with ui.row().classes(
                            "items-center gap-1 px-2 py-0.5 rounded-md "
                            "bg-[#2b2f3d] border border-[#3b82f6]/30"
                        ):
                            ui.icon("insert_drive_file", size="12px").classes(
                                "text-[#8b949e]"
                            )
                            ui.label(chip.text).classes(
                                "text-xs text-[#e6edf3] truncate max-w-[160px]"
                            )
                            ui.icon("close", size="10px").classes(
                                "text-[#64748b] cursor-pointer"
                            ).on(
                                "click",
                                lambda _, i=idx: state.remove_selected_mention(i),
                            )

        chips_view()

        last_chips_state = [
            (len(state.pending_attachments), len(state.selected_mentions))
        ]

        def _on_chips_check() -> None:
            cur = (len(state.pending_attachments), len(state.selected_mentions))
            if cur != last_chips_state[0]:
                last_chips_state[0] = cur
                chips_view.refresh()

        state.subscribe(_on_chips_check)

        # Autocomplete service wrapper
        with ui.column().classes("relative w-full"):
            placeholder_text = "Ask Mvge anything… (@ to mention, / for commands)"
            prompt_input = (
                ui.textarea(placeholder=placeholder_text)
                .props("autogrow borderless dense rows=2")
                .classes("w-full bg-transparent text-sm text-[#e6edf3] resize-none")
                .mark("prompt_input")
            )

            # Sync active_prompt if set externally (e.g. example prompts)
            last_active_prompt = [state.active_prompt]

            def _on_prompt_check() -> None:
                if state.active_prompt and state.active_prompt != last_active_prompt[0]:
                    last_active_prompt[0] = state.active_prompt
                    prompt_input.value = state.active_prompt
                    state.active_prompt = ""

            state.subscribe(_on_prompt_check)

            # Bind input to autocomplete service
            def handle_input_change(e: Any) -> None:
                val = getattr(e, "value", None)
                if val is None and hasattr(e, "args"):
                    val = e.args
                text = str(val if val is not None else (prompt_input.value or ""))
                ac_service.on_text_change(text, len(text))

            prompt_input.on("update:model-value", handle_input_change)

            def handle_submit() -> None:
                text = prompt_input.value or ""
                if not text.strip() and not state.selected_mentions:
                    return
                # Prepend mentions to text if any
                if state.selected_mentions:
                    prefix = " ".join(m.text for m in state.selected_mentions) + " "
                    text = prefix + text
                    state.clear_selected_mentions()
                prompt_input.value = ""
                ac_service.close()
                _scroll_to_bottom(element_id=None, force=True)
                state.submit_prompt(text)

            def handle_enter(e: object) -> None:
                # If autocomplete popup is open, enter selects the item
                if ac_service.is_open:
                    item = ac_service.get_selected_item()
                    if item:
                        _apply_autocomplete_selection(
                            ac_service, prompt_input, item, state
                        )
                    return
                # Shift+Enter inserts newline, normal Enter submits
                handle_submit()

            def handle_tab(e: object) -> None:
                if ac_service.is_open:
                    item = ac_service.get_selected_item()
                    if item:
                        _apply_autocomplete_selection(
                            ac_service, prompt_input, item, state
                        )

            def handle_arrow_down(e: object) -> None:
                if ac_service.is_open:
                    ac_service.select_next()

            def handle_arrow_up(e: object) -> None:
                if ac_service.is_open:
                    ac_service.select_prev()

            prompt_input.on("keydown.tab.prevent", handle_tab)
            prompt_input.on("keydown.down.prevent", handle_arrow_down)
            prompt_input.on("keydown.up.prevent", handle_arrow_up)

            prompt_input.on(
                "keydown.backspace",
                lambda e: _handle_backspace(prompt_input, state),
            )

            prompt_input.on("keydown.enter.prevent", handle_enter)
            prompt_input.on("keydown.escape.prevent", ac_service.close)

            # Autocomplete popup
            @ui.refreshable
            def popup_view() -> None:
                if not ac_service.is_open:
                    return
                items = ac_service.get_visible_items()
                if not items:
                    return
                popup_id = f"autocomplete-popup-{id(ac_service)}"
                selected_idx = ac_service.selected_index
                with (
                    ui.element("div")
                    .classes(
                        "absolute z-50 w-full bg-[#2b2f3d] "
                        "border border-[#3b82f6] rounded-lg shadow-xl "
                        "max-h-48 overflow-y-auto bottom-full mb-1"
                    )
                    .props(f"id={popup_id}")
                ):
                    for idx, item in enumerate(items):
                        is_selected = idx == selected_idx
                        item_cls = (
                            "bg-[#3b82f6]/20"
                            if is_selected
                            else "hover:bg-[#2b2f3d]/50"
                        )
                        with (
                            ui.row()
                            .classes(
                                f"items-center gap-2 px-2 py-1 cursor-pointer "
                                f"{item_cls} rounded w-full"
                            )
                            .on(
                                "click",
                                lambda _, i=idx: _select_autocomplete_item(
                                    ac_service, prompt_input, i, state
                                ),
                            )
                            .props(f'data-index="{idx}"')
                        ):
                            ui.icon("help_outline", size="14px").classes(
                                "text-[#8b949e]"
                            )
                            ui.label(str(ac_service.get_item_label(item))).classes(
                                "text-xs text-[#e6edf3] truncate"
                            )

                if items and 0 <= selected_idx < len(items):
                    ui.run_javascript(f"""
                        const container = document.getElementById('{popup_id}');
                        const item = container?.querySelector(
                            '[data-index="{selected_idx}"]'
                        );
                        if (item) item.scrollIntoView({{ block: 'nearest' }});
                    """)

            ac_service.subscribe_items_changed(popup_view.refresh)
            popup_view()

            # Toolbar row
            with ui.row().classes("w-full items-center justify-between pt-1"):
                with ui.row().classes("items-center gap-2"):  # noqa: SIM117
                    with (
                        ui.button(icon="add")
                        .props("flat dense round text-color=grey-4 size=sm")
                        .on(
                            "click",
                            lambda: ui.notify("File upload not yet implemented"),
                        )
                    ):
                        ui.tooltip("Add context files")

                    ui.select(
                        options=get_model_options(),
                        value=state.selected_model,
                        on_change=lambda e: state.switch_model(e.value),
                        with_input=True,
                    ).props("dense borderless dark rounded text-xs").classes(
                        "text-xs text-[#8b949e] font-mono"
                    )

                @ui.refreshable
                def action_btn_view() -> None:
                    with ui.row().classes("items-center gap-2"):
                        if state.is_channeling:
                            with (
                                ui.button(
                                    icon="stop",
                                    on_click=state.stop_channeling,
                                )
                                .props(
                                    "unelevated dense round color=red "
                                    "text-color=white size=sm"
                                )
                                .classes("shadow bg-[#ef4444] hover:bg-[#dc2626]")
                                .mark("stop_channeling_btn")
                            ):
                                ui.tooltip("Stop generation")
                        else:
                            with (
                                ui.button(
                                    icon="arrow_forward",
                                    on_click=handle_submit,
                                )
                                .props(
                                    "unelevated dense round color=primary "
                                    "text-color=white size=sm"
                                )
                                .classes("bg-[#3b82f6] hover:bg-[#2563eb] shadow")
                            ):
                                ui.tooltip("Send prompt")

                action_btn_view()

                last_action_state = [state.is_channeling]

                def _on_action_check() -> None:
                    if state.is_channeling != last_action_state[0]:
                        last_action_state[0] = state.is_channeling
                        action_btn_view.refresh()

                state.subscribe(_on_action_check)


def _toolbar_button(
    icon: str,
    title: str,
    active: bool = False,
    on_click: Callable[[], Any] | None = None,
) -> None:
    """Render a toolbar icon button."""
    btn_cls = (
        "bg-card text-primary"
        if active
        else "text-dim hover:text-secondary hover:bg-highlight"
    )
    with (
        ui.button(icon=icon, on_click=on_click)
        .props("flat dense round size=xs")
        .classes(f"{btn_cls} p-0.5")
    ):
        ui.tooltip(title)


def _copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard."""
    copy_to_clipboard(text)


def _scroll_to_bottom(element_id: int | None = None, force: bool = False) -> None:
    """Smart auto-scroll chat messages to bottom or preserve user scroll position.

    If force is True or the user is already near the bottom, scrolls to bottom.
    If the user has manually scrolled up to read history, preserves scroll position.
    Shows/hides the floating down-arrow button based on bottom-pinning status.
    """
    force_js = "true" if force else "false"
    target_el = f"getElement({element_id})" if element_id is not None else "null"
    js_cmd = f"""
        const el = typeof getElement === 'function'
            ? {target_el}
            : document.getElementById('chat-messages-area');
        const updateScrollBtn = (isPinned) => {{
            const btn = document.getElementById('chat-scroll-bottom-btn');
            if (btn) {{
                if (!isPinned) {{
                    btn.classList.remove('opacity-0', 'pointer-events-none');
                    btn.classList.add('opacity-100', 'pointer-events-auto');
                }} else {{
                    btn.classList.remove('opacity-100', 'pointer-events-auto');
                    btn.classList.add('opacity-0', 'pointer-events-none');
                }}
            }}
        }};
        if (el) {{
            if (!el._scrollListenerAttached) {{
                el._scrollListenerAttached = true;
                el._autoScrollPinned = true;
                el.addEventListener('scroll', () => {{
                    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
                    el._autoScrollPinned = dist < 100;
                    if (!el._autoScrollPinned) {{
                        el._savedScrollTop = el.scrollTop;
                    }}
                    updateScrollBtn(el._autoScrollPinned);
                }});
            }}
            const forceScroll = {force_js};
            if (forceScroll) {{
                el._autoScrollPinned = true;
            }}
            updateScrollBtn(el._autoScrollPinned !== false);
            if (forceScroll || el._autoScrollPinned !== false) {{
                el.scrollTop = el.scrollHeight;
                requestAnimationFrame(() => {{
                    el.scrollTop = el.scrollHeight;
                }});
            }} else if (el._savedScrollTop !== undefined) {{
                el.scrollTop = el._savedScrollTop;
            }}
        }}
    """
    with contextlib.suppress(Exception):
        ui.run_javascript(js_cmd)


def _fill_composer(state: AppState, text: str) -> None:
    """Fill the composer with example text without sending."""
    state.active_prompt = text
    state.notify()


def _handle_backspace(prompt_input: ui.textarea, state: AppState) -> None:
    """Remove the last mention chip if textarea is empty."""
    text = prompt_input.value or ""
    if not text and state.selected_mentions:
        state.remove_selected_mention(len(state.selected_mentions) - 1)


def _apply_autocomplete_selection(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    item: object,
    state: AppState,
) -> None:
    """Apply selected autocomplete item."""
    chip = ac_service.create_chip(item)
    if chip:
        state.add_mention(chip)
        text = prompt_input.value or ""
        start, end = ac_service.get_word_range(text)
        if start >= 0 and end >= 0:
            prompt_input.value = text[:start] + text[end:]
    ac_service.close()
    ac_service._notify_listeners()


def _select_autocomplete_item(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    idx: int,
    state: AppState,
) -> None:
    """Select an autocomplete item and insert as chip."""
    if idx < 0 or idx >= len(ac_service.items):
        return
    ac_service.selected_index = idx
    item = ac_service.items[idx]
    _apply_autocomplete_selection(ac_service, prompt_input, item, state)
