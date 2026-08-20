"""Floating bottom input card dock component with autocomplete and attachments."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from nicegui import ui

from mvgeos_gui.autocomplete import (
    AutocompleteService,
    CommandKind,
    MentionChip,
    MentionItem,
    MentionKind,
)
from mvgeos_gui.model_catalog import get_model_options

if TYPE_CHECKING:
    from mvgeos_gui.state import AppState


def _truncate(text: str, length: int) -> str:
    """Truncate text to fit within footer width."""
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


FILE_TYPE_ICONS: dict[str, str] = {
    ".c": "code",
    ".cc": "code",
    ".cmake": "build",
    ".cpp": "code",
    ".cs": "code",
    ".css": "css",
    ".cxx": "code",
    ".dockerfile": "docker",
    ".env": "key",
    ".env.example": "key",
    ".env.local": "key",
    ".fs": "code",
    ".go": "code",
    ".gradle": "build",
    ".groovy": "code",
    ".h": "code",
    ".hpp": "code",
    ".hxx": "code",
    ".htm": "code",
    ".html": "code",
    ".ini": "settings",
    ".java": "code",
    ".js": "javascript",
    ".json": "data_object",
    ".json5": "data_object",
    ".jsonc": "data_object",
    ".kt": "code",
    ".kts": "code",
    ".less": "css",
    ".lua": "code",
    ".md": "description",
    ".mdx": "description",
    ".mjs": "javascript",
    ".mts": "code",
    ".pdf": "picture_as_pdf",
    ".pl": "code",
    ".pm": "code",
    ".png": "image",
    ".ps1": "terminal",
    ".psm1": "terminal",
    ".py": "code",
    ".pyi": "code",
    ".pyw": "code",
    ".rb": "code",
    ".rs": "code",
    ".rst": "description",
    ".sass": "css",
    ".scala": "code",
    ".scss": "css",
    ".sh": "terminal",
    ".styl": "css",
    ".swift": "code",
    ".toml": "data_object",
    ".ts": "code",
    ".tsv": "table_chart",
    ".tsx": "code",
    ".txt": "description",
    ".vb": "code",
    ".vue": "code",
    ".xml": "data_object",
    ".yaml": "data_object",
    ".yml": "data_object",
    "build.gradle": "build",
    "changelog": "history",
    "cmake": "build",
    "cmakelists.txt": "build",
    "contributing": "description",
    "docker-compose.yaml": "docker",
    "docker-compose.yml": "docker",
    "dockerfile": "docker",
    "license": "policy",
    "makefile": "build",
    "makefile.am": "build",
    "makefile.in": "build",
    "pom.xml": "build",
    "readme": "description",
}

DEFAULT_FILE_ICON = "insert_drive_file"


def _get_file_icon(path: Path) -> str:
    """Return the appropriate Material icon name for a file
    based on its extension or name.
    """
    suffix = path.suffix.lower()
    if suffix in FILE_TYPE_ICONS:
        return FILE_TYPE_ICONS[suffix]
    name = path.name.lower()
    if name in FILE_TYPE_ICONS:
        return FILE_TYPE_ICONS[name]
    return DEFAULT_FILE_ICON


def _autocomplete_icon(kind_str: str) -> str:
    """Return the NiceGUI icon name for an autocomplete item kind."""
    if kind_str == MentionKind.FILE:
        return "insert_drive_file"  # fallback, actual icon resolved per-file
    if kind_str == MentionKind.SKILL:
        return "auto_awesome"
    if kind_str == CommandKind.SLASH:
        return "slash"
    if kind_str == CommandKind.RUNE:
        return "auto_awesome"
    return "help_outline"


def _autocomplete_icon_color(kind_str: str) -> str:
    """Return the CSS color class for an autocomplete item kind icon."""
    if kind_str == MentionKind.FILE:
        return "text-[#8b949e]"
    if kind_str in (MentionKind.SKILL, CommandKind.RUNE):
        return "text-[#3b82f6]"
    return "text-[#8b949e]"


def _chip_icon_for_kind(kind_str: str, chip: MentionChip) -> str:
    """Return the icon name for a mention chip."""
    if kind_str == MentionKind.FILE and chip.path:
        return _get_file_icon(chip.path)
    if kind_str == MentionKind.SKILL:
        return "auto_awesome"
    if kind_str == CommandKind.SLASH:
        return "slash"
    if kind_str == CommandKind.RUNE:
        return "auto_awesome"
    return "help_outline"


def _chip_icon_color_for_kind(kind_str: str) -> str:
    """Return the CSS color class for a mention chip icon."""
    if kind_str == MentionKind.FILE:
        return "text-[#8b949e]"
    if kind_str in (MentionKind.SKILL, CommandKind.RUNE):
        return "text-[#3b82f6]"
    return "text-[#8b949e]"


def _render_mention_chips(state: AppState) -> None:
    """Render selected mention chips above the textarea."""
    if not state.selected_mentions:
        return

    with ui.row().classes("items-center gap-1.5 flex-wrap"):
        for idx, chip in enumerate(state.selected_mentions):
            with ui.row().classes(
                "items-center gap-1 px-2 py-0.5 rounded-md "
                "bg-[#2b2f3d] border border-[#3b82f6]/30 text-[#e6edf3] text-xs"
            ):
                ui.icon(_chip_icon_for_kind(chip.kind, chip), size="12px").classes(
                    _chip_icon_color_for_kind(chip.kind)
                )
                ui.label(chip.text).classes("truncate max-w-[160px]")
                ui.icon("close", size="10px").classes(
                    "text-[#64748b] cursor-pointer"
                ).on(
                    "click",
                    lambda _, i=idx: _remove_mention_chip(state, i),
                )


def _remove_mention_chip(state: AppState, index: int) -> None:
    """Remove a mention chip by index."""
    if 0 <= index < len(state.selected_mentions):
        state.selected_mentions.pop(index)
        state.notify()


def render_input_dock(state: AppState) -> ui.column:
    """Render floating input dock at bottom of conversation viewport.

    Includes textarea with @-mention and /-slash autocomplete popups,
    attachment chips, file upload button, model selector, and submit/stop
    controls.
    """
    ac_service = state.get_autocomplete_service()
    wrapper = ui.column().classes("w-full px-6 pb-6 pt-2 shrink-0")

    with wrapper:
        card = ui.card().classes(
            "w-full bg-[#1e212b] border border-[#2b2f3d] "
            "rounded-2xl p-3 gap-3 shadow-2xl relative "
            "focus-within:border-[#3b82f6] transition-colors"
        )

        with card:
            _render_mention_chips(state)

            def on_value_change(_e: object) -> None:
                ac_service.process_input(state.active_prompt)

            prompt_input = (
                ui.textarea(
                    placeholder="Ask anything. @ to mention. / for actions",
                    on_change=on_value_change,
                )
                .props("borderless autogrow dark dense hide-bottom-space")
                .classes(
                    "w-full text-xs text-[#e6edf3] bg-transparent resize-none "
                    "leading-relaxed min-h-[36px] px-1"
                )
            )
            prompt_input.bind_value(state, "active_prompt")

            def handle_submit() -> None:
                text = (prompt_input.value or "").strip()
                if text or state.selected_mentions:
                    state.active_prompt = ""
                    ac_service.close()
                    state.submit_prompt(text)

            def handle_enter() -> None:
                if ac_service.is_open:
                    item = ac_service.items[ac_service.selected_index]
                    chip = ac_service.create_chip(item)
                    if chip:
                        state.add_mention(chip)
                        text = prompt_input.value or ""
                        start, end = ac_service.get_word_range(text)
                        if start >= 0 and end >= 0:
                            prompt_input.value = text[:start] + text[end:]
                    ac_service.close()
                else:
                    handle_submit()

            prompt_input.on("keydown.enter.prevent", handle_enter)
            prompt_input.on("keydown.escape.prevent", ac_service.close)
            prompt_input.on(
                "keydown.down.prevent",
                lambda _: _handle_arrow_navigation(ac_service, prompt_input, 1),
            )
            prompt_input.on(
                "keydown.up.prevent",
                lambda _: _handle_arrow_navigation(ac_service, prompt_input, -1),
            )
            prompt_input.on(
                "keydown.tab",
                lambda _: _handle_tab(ac_service, prompt_input, state),
            )
            prompt_input.on(
                "keydown.backspace",
                lambda _: _handle_backspace(state, prompt_input),
            )

            # Create a refreshable popup that only re-renders when items change
            # (not on selection change). Selection is handled via JavaScript.
            @ui.refreshable
            def popup_view() -> None:
                _render_autocomplete_popup(ac_service, prompt_input, state)

            # Subscribe to items changes only (open/close, query filter).
            # Selection changes are handled via JavaScript for responsiveness.
            ac_service.subscribe_items_changed(popup_view.refresh)

            popup_view()
            _render_mention_chips(state)
            _render_attachment_chips(state)

            with ui.row().classes("w-full items-center justify-between px-1"):
                _render_left_toolbar(state)
                _render_right_toolbar(state, handle_submit)

    return wrapper


def _render_autocomplete_popup(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    state: AppState,
) -> None:
    """Render autocomplete suggestion popup above the textarea."""
    if not ac_service.is_open:
        return

    items = ac_service.get_visible_items()
    if not items:
        return

    # Unique ID for the popup container to enable autoscroll
    popup_id = f"autocomplete-popup-{id(ac_service)}"
    selected_idx = ac_service.selected_index

    with (
        ui.element("div")
        .classes(
            "absolute z-50 w-full bg-[#2b2f3d] border border-[#3b82f6] "
            "rounded-lg shadow-xl max-h-48 overflow-y-auto bottom-full mb-1"
        )
        .props(f"id={popup_id}")
    ):
        for idx, item in enumerate(items):
            _render_autocomplete_item(
                ac_service, prompt_input, item, idx, popup_id, state
            )

    # Auto-scroll to selected item
    if items and 0 <= selected_idx < len(items):
        ui.run_javascript(f"""
            const container = document.getElementById('{popup_id}');
            const item = container?.querySelector('[data-index="{selected_idx}"]');
            if (item) {{
                item.scrollIntoView({{ block: 'nearest' }});
            }}
        """)


def _render_autocomplete_item(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    item: object,
    idx: int,
    popup_id: str,
    state: AppState,
) -> None:
    """Render a single autocomplete popup item row."""
    is_selected = idx == ac_service.selected_index
    bg_class = "bg-[#3b82f6]/20" if is_selected else "hover:bg-[#2b2f3d]/50"

    kind_str = ac_service.get_item_kind(item)
    is_file = kind_str == MentionKind.FILE

    with (
        ui.row()
        .classes(
            f"items-center gap-2 px-2 py-1 cursor-pointer {bg_class} rounded w-full"
        )
        .on(
            "click",
            lambda _, i=idx: _select_item(ac_service, prompt_input, i, state),
        )
        .props(f'data-index="{idx}"')
    ):
        kind_str = ac_service.get_item_kind(item)
        is_file = kind_str == MentionKind.FILE

        if is_file and isinstance(item, MentionItem) and item.path:
            file_icon = _get_file_icon(item.path)
            ui.icon(file_icon, size="14px").classes("text-[#8b949e]")
        else:
            ui.icon(_autocomplete_icon(kind_str), size="14px").classes(
                _autocomplete_icon_color(kind_str)
            )

        label = ac_service.get_item_label(item)
        description = ac_service.get_item_description(item)

        if is_file and isinstance(item, MentionItem) and item.path:
            # For files: show filename on left, relative path on right
            filename = item.path.name
            file_icon = _get_file_icon(item.path)
            # Get relative path from project root
            try:
                project_path = ac_service._mention_index._project_path
                rel_path = item.path.relative_to(project_path)
                path_str = str(rel_path)
                # If file is in root of cwd, show cwd name/
                if rel_path == Path(filename):
                    path_str = f"{project_path.name}/"
            except ValueError:
                path_str = str(item.path)

            with ui.row().classes("items-center gap-2 w-full"):
                # File type icon + filename on left
                with ui.row().classes("items-center gap-1.5"):
                    ui.icon(file_icon, size="14px").classes("text-[#8b949e]")
                    ui.label(_truncate(filename, 28)).classes(
                        "text-xs text-[#e6edf3] truncate font-medium"
                    )
                # Relative path on right (description style) - more visible
                if path_str != filename:
                    ui.label(_truncate(path_str, 50)).classes(
                        "text-[10px] text-[#94a3b8] truncate italic ml-auto"
                    )
        else:
            # For skills, commands, etc.: original layout
            with ui.column().classes("flex-1 min-w-0"):
                ui.label(_truncate(str(label), 40)).classes(
                    "text-xs text-[#e6edf3] truncate"
                )
                if description:
                    ui.label(_truncate(str(description), 50)).classes(
                        "text-[10px] text-[#64748b] truncate"
                    )


def _render_attachment_chips(state: AppState) -> None:
    """Render attachment chip row when there are pending attachments."""
    if not state.pending_attachments:
        return

    with ui.row().classes("items-center gap-1.5 mt-1 flex-wrap"):
        for idx, name in enumerate(state.pending_attachments):
            with ui.row().classes(
                "items-center gap-1 px-2 py-0.5 rounded-md "
                "bg-[#2b2f3d] text-[#e6edf3] text-xs"
            ):
                ui.icon("insert_drive_file", size="12px").classes("text-[#8b949e]")
                ui.label(_truncate(str(name), 36)).classes("truncate max-w-[140px]")
                ui.icon("close", size="10px").classes("text-[#64748b]").on(
                    "click",
                    lambda _, i=idx: state.remove_attachment(i),
                )


def _handle_upload(e: object, state: AppState) -> None:
    """Handle file upload from the upload component."""
    # NiceGUI's upload event contains the uploaded file info
    # The event structure varies, try to extract file info
    try:
        # e.args contains the upload event data
        if hasattr(e, "args") and e.args:
            args = e.args
            if isinstance(args, dict):
                name = (
                    args.get("name")
                    or args.get("fileName")
                    or args.get("file", {}).get("name")
                )
                if name:
                    state.add_attachment(name)
    except Exception:
        pass  # Silently ignore upload errors


def _render_left_toolbar(state: AppState) -> None:
    """Render left-side toolbar: attach button, model selector, mode pill."""
    with ui.row().classes("items-center gap-2"):
        # Upload component for file attachments
        ui.upload(
            on_upload=lambda e: _handle_upload(e, state),
            auto_upload=True,
        ).props(
            "accept=.png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.txt,.md,.py,.js,.ts,.json,.yaml,.yml,.toml,.csv,.html,.css,.sh,.rs,.go,.java,.cpp,.cs,.rb,.php,.swift,.kt,.scala,.r,.lua,.pl,.php,.sql,.rst,.adoc,.tex,.ini,.cfg,.conf,.config,.env,.gitignore,.dockerfile,.dockerignore,.editorconfig,.prettierrc,.eslintrc,.babelrc,.stylelintrc,.gitignore,.gitattributes,.gitmodules,Dockerfile,Makefile,LICENSE,README,CHANGELOG,CONTRIBUTING"
        ).classes("hidden").mark("file_upload")

        with (
            ui.button(icon="add")
            .props("flat dense round text-color=grey-4 size=sm")
            .on("click", lambda: ui.get_element_by_id("file_upload").pickFiles())  # type: ignore[operator]
            .mark("attach_files_btn")
        ):
            ui.tooltip("Add context files or images")

        ui.select(
            options=get_model_options(),
            value=state.selected_model,
            on_change=lambda e: state.switch_model(e.value),
            with_input=True,
        ).props(
            "dense options-dense borderless dark options-dark rounded text-xs"
        ).classes("text-xs text-[#8b949e] font-mono max-w-[220px]")

        with ui.row().classes(
            "items-center gap-1 px-2 py-0.5 rounded bg-[#13151b] border "
            "border-[#2b2f3d] text-[11px] text-[#8b949e] cursor-pointer"
        ):
            ui.icon("terminal", size="12px").classes("text-[#3b82f6]")
            ui.label("Local").classes("font-normal")
            ui.icon("expand_more", size="12px")


def _render_right_toolbar(state: AppState, handle_submit: object) -> None:
    """Render right-side toolbar: mic button and submit/stop button."""
    with ui.row().classes("items-center gap-2"):
        with ui.button(icon="mic").props("flat dense round text-color=grey-5 size=sm"):
            ui.tooltip("Voice Input")

        if state.is_channeling:
            with (
                ui.button(
                    icon="stop",
                    on_click=lambda: state.stop_channeling(),
                )
                .props("unelevated dense round color=red text-color=white size=sm")
                .classes("shadow bg-[#ef4444] hover:bg-[#dc2626]")
                .mark("stop_channeling_btn")
            ):
                ui.tooltip("Stop generation")
        else:
            with (
                ui.button(
                    icon="arrow_forward",
                    on_click=lambda: handle_submit(),  # type: ignore[operator]
                )
                .props("unelevated dense round color=primary text-color=white size=sm")
                .classes("bg-[#3b82f6] hover:bg-[#2563eb] shadow")
                .mark("submit_prompt_btn")
            ):
                ui.tooltip("Send prompt")


def _handle_tab(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    state: AppState,
) -> None:
    """Handle Tab key to select current autocomplete item as a chip."""
    if not ac_service.is_open or not ac_service.items:
        return

    item = ac_service.items[ac_service.selected_index]
    chip = ac_service.create_chip(item)
    if chip:
        state.add_mention(chip)
        text = prompt_input.value or ""
        start, end = ac_service.get_word_range(text)
        if start >= 0 and end >= 0:
            prompt_input.value = text[:start] + text[end:]
    ac_service.close()


def _select_item(
    ac_service: AutocompleteService,
    prompt_input: ui.textarea,
    idx: int,
    state: AppState,
) -> None:
    """Select an autocomplete item by index (from click) as a chip."""
    if idx < 0 or idx >= len(ac_service.items):
        return
    ac_service.selected_index = idx
    item = ac_service.items[idx]
    chip = ac_service.create_chip(item)
    if chip:
        state.add_mention(chip)
        text = prompt_input.value or ""
        start, end = ac_service.get_word_range(text)
        if start >= 0 and end >= 0:
            prompt_input.value = text[:start] + text[end:]
    ac_service.close()
    ac_service._notify_listeners()


def _handle_backspace(state: AppState, prompt_input: ui.textarea) -> None:
    """Handle Backspace to remove the last chip when textarea is empty."""
    if prompt_input.value or not state.selected_mentions:
        return
    state.remove_last_mention()


def _handle_arrow_navigation(
    ac_service: AutocompleteService, prompt_input: ui.textarea, direction: int
) -> None:
    """Handle arrow up/down navigation with JavaScript-based selection update.
    Updates selection index on server and uses JavaScript to update
    the highlighted item and scroll it into view - no full re-render.
    """
    if not ac_service.is_open or not ac_service.items:
        return

    # Update selection index on server
    new_index = ac_service.selected_index + direction
    if new_index < 0:
        new_index = 0
    elif new_index >= len(ac_service.items):
        new_index = len(ac_service.items) - 1
    ac_service.selected_index = new_index

    # Update highlight and scroll via JavaScript (no re-render)
    popup_id = f"autocomplete-popup-{id(ac_service)}"
    ui.run_javascript(f"""
        const container = document.getElementById('{popup_id}');
        if (!container) return;

        // Remove old selection
        const oldSelected = container.querySelector('[data-selected="true"]');
        if (oldSelected) {{
            oldSelected.removeAttribute('data-selected');
            oldSelected.classList.remove('bg-[#3b82f6]/20');
            oldSelected.classList.add('hover:bg-[#2b2f3d]/50');
        }}

        // Add new selection
        const newSelected = container.querySelector('[data-index="{new_index}"]');
        if (newSelected) {{
            newSelected.setAttribute('data-selected', 'true');
            newSelected.classList.remove('hover:bg-[#2b2f3d]/50');
            newSelected.classList.add('bg-[#3b82f6]/20');
            newSelected.scrollIntoView({{ block: 'nearest' }});
        }}
    """)
