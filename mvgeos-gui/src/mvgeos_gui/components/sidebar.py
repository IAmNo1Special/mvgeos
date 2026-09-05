"""Left navigation sidebar for MvgeOS desktop."""

from nicegui import app, ui

from mvgeos_gui import __version__
from mvgeos_gui.components.sidebar_hint import sidebar_hint
from mvgeos_gui.state import AppState


def render_sidebar(state: AppState) -> ui.column:
    """Render the collapsible left sidebar."""
    collapsed = app.storage.user.get("sidebar-collapsed", False)
    collapsed_width = 80
    expanded_width = 260

    container = (
        ui.column()
        .classes(
            "h-full bg-[#13151b] border-r border-[#2b2f3d] "
            "shrink-0 flex flex-col sidebar-container"
        )
        .style(f"width: {collapsed_width if collapsed else expanded_width}px")
    )

    with container:
        # Header
        with ui.row().classes(
            "w-full h-12 items-center justify-between px-3 border-b border-[#2b2f3d]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("auto_awesome", size="16px").classes("text-[#3b82f6]")
                ui.label("MvgeOS").classes(
                    "text-sm font-semibold text-[#e6edf3] tracking-wide "
                    "sidebar-label" + (" collapsed" if collapsed else " expanded")
                )
            ui.button(
                icon="chevron_left",
                on_click=_toggle_sidebar,
            ).props(
                "flat dense round text-color=grey-5 size=xs collapse-btn-icon"
                + (" collapsed" if collapsed else "")
            )

        # Workspace / Project display
        with ui.row().classes("px-3 py-2 items-center gap-2"):
            ui.icon("folder_open", size="14px").classes("text-[#3b82f6]")
            project_name = state.project_path.name or str(state.project_path)
            ui.label(project_name).classes(
                "text-xs text-[#e6edf3] truncate font-medium sidebar-label"
                + (" collapsed" if collapsed else " expanded")
            )

        # New Conversation button / Sign In
        if state.current_user:
            with ui.row().classes("px-3 py-1"):
                ui.button(
                    "+ New Conversation",
                    on_click=state.new_conversation,
                ).props("unelevated no-caps").classes(
                    "w-full bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] "
                    "border border-[#2b2f3d] text-xs font-medium py-2 "
                    "rounded-lg text-left pl-3 sidebar-label"
                    + (" collapsed" if collapsed else " expanded")
                ).mark("new_conversation_btn")
        else:
            with ui.row().classes("px-3 py-1"):
                ui.button(
                    "Sign In",
                    on_click=state.show_login,
                ).props("unelevated no-caps").classes(
                    "w-full bg-[#3b82f6] hover:bg-blue-600 "
                    "text-white text-xs font-medium py-2 rounded-lg "
                    "sidebar-label" + (" collapsed" if collapsed else " expanded")
                ).mark("sign_in_btn")

        # Navigation items
        with ui.column().classes("px-2 py-1 gap-0.5"):
            _sidebar_item(
                "Home", "home", "home", state.current_view == "home", state, collapsed
            )
            _sidebar_item(
                "Chat",
                "chat",
                "chat_bubble_outline",
                state.current_view == "chat",
                state,
                collapsed,
            )
            _sidebar_item(
                "Sessions",
                "sessions",
                "history",
                state.current_view == "sessions",
                state,
                collapsed,
            )
            _sidebar_item(
                "Timeline",
                "timeline",
                "activity",
                state.current_view == "timeline",
                state,
                collapsed,
            )
            _sidebar_item(
                "Packages",
                "packages",
                "package",
                state.current_view == "packages",
                state,
                collapsed,
            )
            _sidebar_item(
                "Notes",
                "notes",
                "sticky_note_2",
                state.current_view == "notes",
                state,
                collapsed,
            )
            _sidebar_item(
                "Skills",
                "skills",
                "auto_awesome",
                state.current_view == "skills",
                state,
                collapsed,
            )
            _sidebar_item(
                "Diagnostics",
                "diagnostics",
                "stethoscope",
                state.current_view == "diagnostics",
                state,
                collapsed,
            )

        ui.separator().classes("my-2")

        with ui.column().classes("px-2 py-1 gap-0.5"):
            _sidebar_item(
                "Settings",
                "settings",
                "settings",
                state.current_view == "settings",
                state,
                collapsed,
            )

        # Current Session
        if state.active_tome_id is not None:
            with (
                ui.row().classes("mx-3 mt-3"),
                ui.card().classes(
                    "w-full p-3 bg-[#1e212b] border border-[#2b2f3d] "
                    "rounded-lg sidebar-label"
                    + (" collapsed" if collapsed else " expanded")
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
        with ui.column().classes(
            "mt-4 flex-1 overflow-y-auto px-2 sidebar-label"
            + (" collapsed" if collapsed else " expanded")
        ):
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
                        .on(
                            "click",
                            lambda _, e=entry: state.switch_to_tome(e.tome_id),
                        )
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

        # Bottom: collapse button + version
        with ui.row().classes("border-t border-[#2b2f3d] px-3 py-2 items-center gap-2"):
            ui.button(
                icon="chevron_left",
                on_click=_toggle_sidebar,
            ).props(
                "flat dense round text-color=grey-5 size=xs "
                "collapse-btn-icon" + (" collapsed" if collapsed else "")
            )
            ui.label(f"v{__version__}").classes(
                "text-[10px] text-[#64748b] sidebar-label"
                + (" collapsed" if collapsed else " expanded")
            )

    return container


def _toggle_sidebar() -> None:
    """Toggle sidebar collapsed state."""
    app.storage.user["sidebar-collapsed"] = not app.storage.user.get(
        "sidebar-collapsed", False
    )


def _sidebar_item(
    label: str,
    view: str,
    icon: str,
    active: bool,
    state: AppState,
    collapsed: bool,
) -> None:
    """Render a single sidebar navigation item."""
    active_cls = (
        "nav-link-active text-primary"
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
        ui.icon(icon, size="14px").classes(
            "shrink-0 " + ("nav-icon-active" if active else "text-[#8b949e]")
        )
        ui.label(label).classes(
            "font-normal truncate sidebar-label"
            + (" collapsed" if collapsed else " expanded")
        )
        if not collapsed:
            sidebar_hint(label)
