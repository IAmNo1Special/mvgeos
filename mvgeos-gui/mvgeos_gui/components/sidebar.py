"""Left navigation sidebar for MvgeOS desktop."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_sidebar(state: AppState) -> ui.column:
    """Render the collapsible left sidebar."""
    container = (
        ui.column()
        .classes("h-full bg-[#13151b] border-r border-[#2b2f3d] shrink-0 flex flex-col")
        .style(f"width: {state._sidebar_width}px")
    )

    with container:
        # Header
        with ui.row().classes(
            "w-full h-12 items-center justify-between px-3 border-b border-[#2b2f3d]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("auto_awesome", size="16px").classes("text-[#3b82f6]")
                ui.label("MvgeOS").classes(
                    "text-sm font-semibold text-[#e6edf3] tracking-wide"
                )
            ui.button(
                icon="view_sidebar",
                on_click=state.toggle_sidebar,
            ).props("flat dense round text-color=grey-5 size=xs").mark(
                "toggle_sidebar_btn"
            )

        # Workspace / Project display
        with ui.row().classes("px-3 py-2 items-center gap-2"):
            ui.icon("folder_open", size="14px").classes("text-[#3b82f6]")
            project_name = state.project_path.name or str(state.project_path)
            ui.label(project_name).classes(
                "text-xs text-[#e6edf3] truncate font-medium"
            )

        # New Conversation button
        with ui.row().classes("px-3 py-1"):
            ui.button(
                "+ New Conversation",
                on_click=state.new_conversation,
            ).props("unelevated no-caps").classes(
                "w-full bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] "
                "border border-[#2b2f3d] text-xs font-medium py-2 "
                "rounded-lg text-left pl-3"
            ).mark("new_conversation_btn")

        # Navigation items
        with ui.column().classes("px-2 py-1 gap-0.5"):
            _sidebar_item("Home", "home", state.current_view == "home", state)
            _sidebar_item("Chat", "chat", state.current_view == "chat", state)
            _sidebar_item(
                "Sessions", "sessions", state.current_view == "sessions", state
            )
            _sidebar_item(
                "Timeline", "timeline", state.current_view == "timeline", state
            )
            _sidebar_item(
                "Packages", "packages", state.current_view == "packages", state
            )
            _sidebar_item("Notes", "notes", state.current_view == "notes", state)
            _sidebar_item("Skills", "skills", state.current_view == "skills", state)
            _sidebar_item(
                "Diagnostics", "diagnostics", state.current_view == "diagnostics", state
            )
            _sidebar_item(
                "Settings", "settings", state.current_view == "settings", state
            )

        # Current Session
        if state.active_tome_id is not None:
            with (
                ui.row().classes("mx-3 mt-3"),
                ui.card().classes(
                    "w-full p-3 bg-[#1e212b] border border-[#2b2f3d] rounded-lg"
                ),
            ):
                ui.label("Current Session").classes(
                    "text-[10px] font-semibold uppercase tracking-wider text-[#64748b]"
                )
                ui.label(state.tome_title).classes(
                    "text-sm text-[#e6edf3] truncate mt-1"
                )
                if state.active_tome_id:
                    ui.label(state.active_tome_id[:8]).classes(
                        "text-[10px] text-[#64748b] font-mono mt-0.5"
                    )

        # Recent Sessions
        with ui.column().classes("mt-4 flex-1 overflow-y-auto px-2"):
            ui.label("Recent Sessions").classes(
                "text-[10px] font-semibold uppercase tracking-wider "
                "text-[#64748b] px-2 py-1"
            )
            if not state.loaded_tomes:
                ui.label("No sessions yet").classes(
                    "text-[11px] text-[#64748b] px-2 py-2"
                )
            else:
                for entry in state.loaded_tomes:
                    bg = (
                        "bg-[#1e212b]/70 border border-[#2b2f3d]/60"
                        if entry.is_active
                        else "hover:bg-[#1e212b]/40"
                    )
                    with (
                        ui.row()
                        .classes(
                            f"w-full items-center px-2 py-1.5 rounded-md "
                            f"cursor-pointer text-xs {bg}"
                        )
                        .on("click", lambda _, e=entry: state.switch_to_tome(e.tome_id))
                    ):
                        ui.icon("chat_bubble_outline", size="12px").classes(
                            "text-[#8b949e]"
                        )
                        ui.label(entry.title).classes(
                            "text-[#e6edf3] truncate text-[11px] flex-1"
                        )
                        with ui.row().classes("items-center gap-1"):
                            ui.label(entry.relative_time).classes(
                                "text-[10px] text-[#64748b]"
                            )
                            if entry.git_branch:
                                ui.label(entry.git_branch).classes(
                                    "text-[10px] px-1 py-0.5 rounded "
                                    "bg-[#3b82f6]/10 text-[#3b82f6] "
                                    "border border-[#3b82f6]/30 font-mono"
                                )

        # Bottom: Settings
        with ui.row().classes("border-t border-[#2b2f3d] px-3 py-2"):
            with (
                ui.row()
                .classes("items-center gap-2 cursor-pointer")
                .on("click", state.open_app_settings)
            ):
                ui.icon("settings", size="14px").classes("text-[#8b949e]")
                ui.label("Settings").classes("text-xs text-[#8b949e]")
            ui.label("v0.1.0").classes("text-[10px] text-[#64748b] ml-auto")

    return container


def _sidebar_item(label: str, view: str, active: bool, state: AppState) -> None:
    """Render a single sidebar navigation item."""
    icon_map = {
        "home": "home",
        "chat": "chat_bubble_outline",
        "sessions": "history",
        "timeline": "activity",
        "packages": "package",
        "notes": "sticky_note_2",
        "skills": "auto_awesome",
        "diagnostics": "stethoscope",
        "settings": "settings",
    }
    active_cls = (
        "bg-card text-primary"
        if active
        else "text-[#8b949e] hover:text-[#e6edf3] hover:bg-[#1e212b]/60"
    )
    with (
        ui.row()
        .classes(
            f"w-full items-center gap-2.5 px-3 py-2 rounded-md "
            f"cursor-pointer text-xs transition-colors {active_cls}"
        )
        .on("click", lambda _, v=view: state.set_current_view(v))
    ):
        ui.icon(icon_map.get(view, "circle"), size="14px").classes(
            "shrink-0 " + ("text-[#3b82f6]" if active else "text-[#8b949e]")
        )
        ui.label(label).classes("font-normal truncate")
