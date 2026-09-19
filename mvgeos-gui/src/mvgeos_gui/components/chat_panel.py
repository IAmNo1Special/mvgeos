"""Main chat panel: toolbar, message list, side panel, and composer."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from nicegui import ui

from mvgeos_gui.autocomplete import AutocompleteService
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
                        on_click=state.open_app_settings,
                        marker="chat_toolbar_settings_btn",
                    )

        toolbar_view()

        last_toolbar_state = [
            (
                state.review_open,
                state.chat_side_panel,
                str(state.project_path),
            )
        ]

        def _on_toolbar_check() -> None:
            cur = (
                state.review_open,
                state.chat_side_panel,
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
                    .classes("flex-1 w-full overflow-y-auto space-y-4")
                    .props('id="chat-messages-area"')
                ) as messages_area:

                    @ui.refreshable
                    def static_messages_view() -> None:
                        if not state.messages:
                            _render_empty_chat(state)
                            return
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

                    static_messages_view()
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

                # Composer
                _render_composer(state)

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


def _render_empty_chat(state: AppState) -> None:
    """Render the centered empty-chat prompt."""
    with ui.column().classes("w-full h-full items-center justify-center px-4"):
        with ui.row().classes(
            "w-14 h-14 rounded-2xl bg-[#0e0e12] border border-[#292335] "
            "items-center justify-center shadow-lg mb-6"
        ):
            ui.icon("auto_awesome", size="28px").classes("text-[#7b6cf6]")

        ui.label("What should Mvge work on?").classes(
            "text-2xl font-semibold text-[#eceaf4] tracking-tight"
        )
        status_text = {
            "channeling": "Mvge is channeling a response…",
            "working": "Mvge is working…",
            "idle": "Choose a project — Mvge starts when you send.",
        }.get(state.mvge_status, "Choose a project — Mvge starts when you send.")
        ui.label(status_text).classes("text-sm text-[#9c94b3] mt-1 mb-8")

        with ui.row().classes("gap-2 flex-wrap justify-center mb-6"):
            for prompt in EXAMPLE_PROMPTS:
                ui.button(
                    prompt,
                    on_click=lambda p=prompt: _fill_composer(state, p),
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


def _render_composer(state: AppState) -> None:
    """Render the bottom composer input area.

    Curvy glow styling adapted from Uiverse.io "curvy-earwig-22" by
    Lakshay-art (MIT License): fluid full-width version with no search
    icon; the filter slot is reused as the send/stop button.
    """
    ac_service = state.get_autocomplete_service()

    # Glow containment: px-8/pb-8 give the halo fringe room to decay before
    # the chat column's overflow:hidden walls (sides/bottom); pt-5 tops up
    # the open messages area. See .mvge-glow note in styles.py.
    with ui.column().classes("w-full px-8 pb-8 pt-5 shrink-0"):  # noqa: SIM117
        with ui.element("div").classes("mvge-poda").mark("composer-curvy"):
            ui.element("div").classes("mvge-glow")
            ui.element("div").classes("mvge-dark-border-bg")
            ui.element("div").classes("mvge-dark-border-bg")
            ui.element("div").classes("mvge-dark-border-bg")
            ui.element("div").classes("mvge-white")
            ui.element("div").classes("mvge-border")
            with ui.element("div").classes("mvge-main").mark("composer-main"):
                # Attachment and Mention chips
                @ui.refreshable
                def chips_view() -> None:
                    if state.pending_attachments:
                        with ui.row().classes("items-center gap-1.5 flex-wrap mb-2"):
                            for idx, name in enumerate(state.pending_attachments):
                                with ui.row().classes(
                                    "items-center gap-1 px-2 py-0.5 rounded-md "
                                    "bg-[#292335]"
                                ):
                                    ui.icon("insert_drive_file", size="12px").classes(
                                        "text-[#9c94b3]"
                                    )
                                    ui.label(name).classes(
                                        "text-xs text-[#eceaf4] truncate max-w-[140px]"
                                    )
                                    ui.icon("close", size="10px").classes(
                                        "text-[#6e6584] cursor-pointer"
                                    ).on(
                                        "click",
                                        lambda _, i=idx: state.remove_attachment(i),
                                    )

                    if state.selected_mentions:
                        with ui.row().classes("items-center gap-1.5 flex-wrap mb-2"):
                            for idx, chip in enumerate(state.selected_mentions):
                                with ui.row().classes(
                                    "items-center gap-1 px-2 py-0.5 rounded-md "
                                    "bg-[#292335] border border-[#7b6cf6]/30"
                                ):
                                    ui.icon("insert_drive_file", size="12px").classes(
                                        "text-[#9c94b3]"
                                    )
                                    ui.label(chip.text).classes(
                                        "text-xs text-[#eceaf4] truncate max-w-[160px]"
                                    )
                                    ui.icon("close", size="10px").classes(
                                        "text-[#6e6584] cursor-pointer"
                                    ).on(
                                        "click",
                                        lambda _, i=idx: state.remove_selected_mention(
                                            i
                                        ),
                                    )

                chips_view()

                last_chips_state = [
                    (len(state.pending_attachments), len(state.selected_mentions))
                ]

                def _on_chips_check() -> None:
                    cur = (
                        len(state.pending_attachments),
                        len(state.selected_mentions),
                    )
                    if cur != last_chips_state[0]:
                        last_chips_state[0] = cur
                        chips_view.refresh()

                state.subscribe_view("composer_chips", _on_chips_check)

                # Input zone: textarea + glow masks + send button
                # (no search icon; filter slot is the send/stop button).
                with ui.column().classes("relative w-full mvge-input-zone"):
                    placeholder_text = (
                        "Ask Mvge anything… (@ to mention, / for commands)"
                    )
                    prompt_input = (
                        ui.textarea(placeholder=placeholder_text)
                        .props("autogrow borderless dense rows=2")
                        .classes(
                            "w-full bg-transparent text-sm text-[#eceaf4] resize-none"
                        )
                        .mark("prompt_input")
                    )
                    ui.element("div").classes("mvge-input-mask")
                    ui.element("div").classes("mvge-pink-mask")
                    ui.element("div").classes("mvge-send-border")

                    # Sync active_prompt if set externally (e.g. example prompts)
                    last_active_prompt = [state.active_prompt]

                    def _on_prompt_check() -> None:
                        if (
                            state.active_prompt
                            and state.active_prompt != last_active_prompt[0]
                        ):
                            last_active_prompt[0] = state.active_prompt
                            prompt_input.value = state.active_prompt
                            state.active_prompt = ""

                    state.subscribe_view("composer_prompt", _on_prompt_check)

                    # Bind input to autocomplete service
                    def handle_input_change(e: Any) -> None:
                        val = getattr(e, "value", None)
                        if val is None and hasattr(e, "args"):
                            val = e.args
                        text = str(
                            val if val is not None else (prompt_input.value or "")
                        )
                        ac_service.process_input(text, len(text))

                    prompt_input.on("update:model-value", handle_input_change)

                    def handle_submit() -> None:
                        text = prompt_input.value or ""
                        if not text.strip() and not state.selected_mentions:
                            return
                        # Prepend mentions to text if any
                        if state.selected_mentions:
                            prefix = (
                                " ".join(m.text for m in state.selected_mentions) + " "
                            )
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

                    def handle_arrow_down(e: object) -> None:
                        if ac_service.is_open:
                            ac_service.move_down()

                    def handle_arrow_up(e: object) -> None:
                        if ac_service.is_open:
                            ac_service.move_up()

                    prompt_input.on(
                        "keydown.tab.prevent",
                        lambda e: handle_tab(ac_service, prompt_input, state),
                    )
                    prompt_input.on("keydown.down.prevent", handle_arrow_down)
                    prompt_input.on("keydown.up.prevent", handle_arrow_up)

                    prompt_input.on(
                        "keydown.backspace",
                        lambda e: _handle_backspace(prompt_input, state),
                    )

                    prompt_input.on("keydown.enter.exact.prevent", handle_enter)
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
                                "absolute z-50 w-full bg-[#292335] "
                                "border border-[#7b6cf6] rounded-lg shadow-xl "
                                "max-h-48 overflow-y-auto bottom-full mb-1"
                            )
                            .props(f"id={popup_id}")
                        ):
                            for idx, item in enumerate(items):
                                is_selected = idx == selected_idx
                                item_cls = (
                                    "bg-[#7b6cf6]/20"
                                    if is_selected
                                    else "hover:bg-[#292335]/50"
                                )
                                with (
                                    ui.row()
                                    .classes(
                                        "items-center gap-2 px-2 py-1 cursor-pointer "
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
                                        "text-[#9c94b3]"
                                    )
                                    ui.label(
                                        str(ac_service.get_item_label(item))
                                    ).classes("text-xs text-[#eceaf4] truncate")

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

                    @ui.refreshable
                    def action_btn_view() -> None:
                        if state.is_channeling:
                            with (
                                ui.button(
                                    icon="stop",
                                    on_click=state.stop_channeling,
                                )
                                .props("unelevated dense size=sm")
                                .classes("mvge-send-btn mvge-stop")
                                .mark("stop_channeling_btn")
                            ):
                                ui.tooltip("Stop generation")
                        else:
                            with (
                                ui.button(
                                    icon="arrow_forward",
                                    on_click=handle_submit,
                                )
                                .props("unelevated dense size=sm")
                                .classes("mvge-send-btn")
                                .mark("send_prompt_btn")
                            ):
                                ui.tooltip("Send prompt")

                    action_btn_view()

                    last_action_state = [state.is_channeling]

                    def _on_action_check() -> None:
                        if state.is_channeling != last_action_state[0]:
                            last_action_state[0] = state.is_channeling
                            action_btn_view.refresh()

                    state.subscribe_view("composer_actions", _on_action_check)

                # Toolbar row below the input (model + context actions)
                with ui.row().classes(
                    "w-full items-center gap-2 pt-1 mvge-composer-toolbar pl-2"
                ):

                    def _handle_upload(e: Any) -> None:
                        """Add uploaded file names as pending attachments."""
                        # e.files is a list of uploaded file objects with .name
                        for f in getattr(e, "files", []):
                            name = getattr(f, "name", "")
                            if name:
                                state.add_attachment(name)
                        if getattr(e, "files", []):
                            ui.notify(
                                f"Added {len(e.files)} attachment(s).",
                                type="positive",
                            )

                    ui.upload(
                        on_upload=_handle_upload,
                        label="",
                    ).props("flat dense round color=grey-5").classes(
                        "mvge-upload-btn"
                    ).mark("composer_upload_btn")

                    @ui.refreshable
                    def cascading_selector_view() -> None:
                        is_router = state.is_router_realm()
                        supports_contemplation = (
                            state.supports_contemplation_for_selected_model()
                        )

                        # Tier 1: Realm Select
                        realms = state.get_realms()
                        realm_labels = {
                            "openrouter": "OpenRouter",
                            "ollama": "Ollama",
                            "google": "Google Direct",
                        }
                        realm_options = {
                            r: realm_labels.get(r, r.capitalize()) for r in realms
                        }
                        with (
                            ui.select(
                                options=realm_options,
                                value=state.selected_realm,
                                on_change=lambda e: state.switch_realm(e.value),
                            )
                            .props("dense borderless dark rounded text-xs")
                            .classes("text-xs text-[#9c94b3] font-mono")
                            .mark("realm_select")
                        ):
                            ui.tooltip("Realm")

                        if state.selected_realm == "openrouter" and not (
                            state.is_rune_installed("openrouter-realm")
                        ):
                            (
                                ui.badge("Rune missing", color="amber-8")
                                .props("rounded dense size=xs")
                                .classes("cursor-pointer")
                                .tooltip("Click to open Marketplace")
                                .on("click", lambda: state.set_current_view("packages"))
                            )

                        # Tier 2: Provider Select (Visible only if router)
                        if is_router:
                            providers = state.get_providers_for_selected_realm()
                            prov_options = {p: p for p in providers}
                            if (
                                state.selected_provider
                                and state.selected_provider not in prov_options
                            ):
                                prov_options[state.selected_provider] = (
                                    state.selected_provider
                                )
                            with (
                                ui.select(
                                    options=prov_options,
                                    value=state.selected_provider,
                                    on_change=lambda e: state.switch_provider(e.value),
                                )
                                .props("dense borderless dark rounded text-xs")
                                .classes("text-xs text-[#9c94b3] font-mono")
                                .mark("provider_select")
                            ):
                                ui.tooltip("Provider")

                        # Tier 3: Model Select
                        model_options = state.get_model_options_for_selection()
                        with (
                            ui.select(
                                options=model_options,
                                value=state.selected_model,
                                on_change=lambda e: state.switch_model(e.value),
                            )
                            .props("dense borderless dark rounded text-xs")
                            .classes("text-xs text-[#9c94b3] font-mono")
                            .mark("model_select")
                        ):
                            ui.tooltip("Model")

                        # Tier 4: Contemplation Level Select (Dynamic, if supported)
                        if supports_contemplation:
                            levels = state.get_contemplation_levels_for_selected_model()
                            level_options = {lvl: f"Thinking: {lvl}" for lvl in levels}
                            if (
                                state.contemplation_level
                                and state.contemplation_level not in level_options
                            ):
                                level_options[state.contemplation_level] = (
                                    f"Thinking: {state.contemplation_level}"
                                )
                            with (
                                ui.select(
                                    options=level_options,
                                    value=state.contemplation_level,
                                    on_change=lambda e: state.set_contemplation_level(
                                        e.value
                                    ),
                                )
                                .props("dense borderless dark rounded text-xs")
                                .classes("text-xs text-[#9c94b3] font-mono")
                                .mark("contemplation_select")
                            ):
                                ui.tooltip("Contemplation Level")

                    cascading_selector_view()

                    last_selector_state = [
                        (
                            state.selected_realm,
                            state.selected_provider,
                            state.selected_model,
                            state.contemplation_level,
                            state.is_rune_installed("openrouter-realm"),
                        )
                    ]

                    def _on_selector_check() -> None:
                        current_sel = (
                            state.selected_realm,
                            state.selected_provider,
                            state.selected_model,
                            state.contemplation_level,
                            state.is_rune_installed("openrouter-realm"),
                        )
                        if current_sel != last_selector_state[0]:
                            last_selector_state[0] = current_sel
                            cascading_selector_view.refresh()

                    state.subscribe_view("cascading_selector", _on_selector_check)


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
                el._userScrolledUp = false;
                el._savedScrollTop = el.scrollTop;

                el.addEventListener('wheel', (e) => {{
                    if (e.deltaY < 0) {{
                        el._userScrolledUp = true;
                        el._savedScrollTop = el.scrollTop;
                        updateScrollBtn(false);
                    }} else if (e.deltaY > 0) {{
                        const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
                        if (dist < 80) {{
                            el._userScrolledUp = false;
                            updateScrollBtn(true);
                        }} else {{
                            el._savedScrollTop = el.scrollTop;
                        }}
                    }}
                }}, {{ passive: true }});

                el.addEventListener('touchmove', () => {{
                    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
                    if (dist >= 80) {{
                        el._userScrolledUp = true;
                        el._savedScrollTop = el.scrollTop;
                        updateScrollBtn(false);
                    }} else {{
                        el._userScrolledUp = false;
                        updateScrollBtn(true);
                    }}
                }}, {{ passive: true }});

                el.addEventListener('scroll', () => {{
                    if (el._isProgrammaticScroll) {{
                        el._isProgrammaticScroll = false;
                        return;
                    }}
                    if (el.scrollHeight > el.clientHeight + 50) {{
                        const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
                        if (dist >= 80) {{
                            el._userScrolledUp = true;
                            el._savedScrollTop = el.scrollTop;
                            updateScrollBtn(false);
                        }} else {{
                            el._userScrolledUp = false;
                            updateScrollBtn(true);
                        }}
                    }}
                }}, {{ passive: true }});
            }}

            const forceScroll = {force_js};
            if (forceScroll) {{
                el._userScrolledUp = false;
            }}

            if (forceScroll || !el._userScrolledUp) {{
                updateScrollBtn(true);
                el._isProgrammaticScroll = true;
                el.scrollTop = el.scrollHeight;
                requestAnimationFrame(() => {{
                    el.scrollTop = el.scrollHeight;
                }});
            }} else {{
                updateScrollBtn(false);
                if (el._savedScrollTop !== undefined) {{
                    el._isProgrammaticScroll = true;
                    el.scrollTop = el._savedScrollTop;
                }}
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


def handle_tab(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    state: AppState,
) -> None:
    """Apply the highlighted autocomplete item when the popup is open."""
    if ac_service.is_open:
        item = ac_service.get_selected_item()
        if item:
            _apply_autocomplete_selection(ac_service, prompt_input, item, state)


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
