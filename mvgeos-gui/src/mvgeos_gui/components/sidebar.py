"""Left navigation sidebar for MvgeOS desktop."""

from nicegui import ui

from mvgeos_gui import __version__
from mvgeos_gui.components.sidebar_hint import sidebar_hint
from mvgeos_gui.state import AppState


def render_sidebar(state: AppState) -> ui.column:
    """Render the collapsible left sidebar."""
    collapsed = not state.sidebar_open
    collapsed_width = 56
    expanded_width = 260

    container = (
        ui.column()
        .classes(
            "h-full bg-[#08080a] border-r border-[#292335] "
            "shrink-0 flex flex-col no-wrap overflow-hidden sidebar-container"
        )
        .style(f"width: {collapsed_width if collapsed else expanded_width}px")
    )

    with container:
        # Header
        if collapsed:
            with (
                ui.row().classes(
                    "w-full h-12 items-center justify-center "
                    "border-b border-[#292335] shrink-0"
                ),
                ui.button(
                    icon="chevron_right",
                    on_click=state.toggle_sidebar,
                )
                .props("flat dense round text-color=grey-5 size=xs")
                .classes("collapse-btn-icon")
                .mark("expand_sidebar_btn"),
            ):
                ui.tooltip("Expand sidebar")
        else:
            with ui.row().classes(
                "w-full h-12 items-center justify-between px-3 "
                "border-b border-[#292335] shrink-0 no-wrap"
            ):
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("auto_awesome", size="16px").classes("text-[#7b6cf6]")
                    ui.label("MvgeOS").classes(
                        "text-sm font-semibold text-[#eceaf4] tracking-wide"
                    )
                with (
                    ui.button(
                        icon="chevron_left",
                        on_click=state.toggle_sidebar,
                    )
                    .props("flat dense round text-color=grey-5 size=xs")
                    .classes("collapse-btn-icon")
                    .mark("collapse_sidebar_btn")
                ):
                    ui.tooltip("Collapse sidebar")

        # Workspace / Project display
        project_name = state.project_path.name or str(state.project_path)
        if collapsed:
            with (
                ui.row().classes("w-full justify-center py-2 shrink-0"),
                ui.element("div").classes(
                    "cursor-pointer p-1.5 rounded-md hover:bg-[#0e0e12]/60"
                ),
            ):
                ui.icon("folder_open", size="16px").classes("text-[#7b6cf6]")
                ui.tooltip(f"Project: {project_name}")
        else:
            with ui.row().classes(
                "w-full px-3 py-2 items-center gap-2 shrink-0 no-wrap"
            ):
                ui.icon("folder_open", size="14px").classes("text-[#7b6cf6] shrink-0")
                ui.label(project_name).classes(
                    "text-xs text-[#eceaf4] truncate font-medium flex-1"
                )

        # New Conversation button / Sign In
        if state.current_user:
            if collapsed:
                with (
                    ui.row().classes("w-full justify-center py-1 shrink-0"),
                    ui.button(
                        icon="add",
                        on_click=state.new_conversation,
                    )
                    .props("flat dense round size=sm")
                    .classes(
                        "bg-[#0e0e12] hover:bg-[#16161d] text-[#eceaf4] "
                        "border border-[#292335]"
                    )
                    .mark("new_conversation_btn"),
                ):
                    ui.tooltip("New Conversation")
            else:
                with ui.row().classes("w-full px-3 py-1 shrink-0"):
                    ui.button(
                        "+ New Conversation",
                        on_click=state.new_conversation,
                    ).props("unelevated no-caps").classes(
                        "w-full bg-[#0e0e12] hover:bg-[#16161d] text-[#eceaf4] "
                        "border border-[#292335] text-xs font-medium py-2 "
                        "rounded-lg text-left pl-3"
                    ).mark("new_conversation_btn")
        else:
            if collapsed:
                with (
                    ui.row().classes("w-full justify-center py-1 shrink-0"),
                    ui.button(
                        icon="login",
                        on_click=state.show_login,
                    )
                    .props("unelevated round size=sm")
                    .classes("mvge-glow-btn text-white")
                    .mark("sign_in_btn"),
                ):
                    ui.tooltip("Sign In")
            else:
                with ui.row().classes("w-full px-3 py-1 shrink-0"):
                    ui.button(
                        "Sign In",
                        on_click=state.show_login,
                    ).props("unelevated no-caps").classes(
                        "w-full mvge-glow-btn "
                        "text-white text-xs font-medium py-2 rounded-lg"
                    ).mark("sign_in_btn")

        # Navigation items
        nav_items = [
            ("Home", "home", "home"),
            ("Chat", "chat", "chat_bubble_outline"),
            ("Sessions", "sessions", "history"),
            ("Timeline", "timeline", "timeline"),
            ("Marketplace", "packages", "storefront"),
            ("Notes", "notes", "sticky_note_2"),
            ("Skills", "skills", "auto_awesome"),
            ("Diagnostics", "diagnostics", "troubleshoot"),
            ("Settings", "settings", "settings"),
        ]

        with ui.column().classes("w-full px-2 py-1 gap-0.5 shrink-0"):
            for label, view, icon in nav_items:
                _sidebar_item(
                    label,
                    view,
                    icon,
                    state.current_view == view,
                    state,
                    collapsed,
                )

        # Current Session & Recent Sessions
        if not collapsed:
            # Current Session
            if state.active_tome_id is not None:
                with (
                    ui.row().classes("mx-3 mt-3 shrink-0"),
                    ui.card().classes(
                        "w-full p-3 bg-[#0e0e12] border border-[#292335] rounded-lg"
                    ),
                ):
                    ui.label("Current Session").classes(
                        "text-[10px] font-semibold uppercase "
                        "tracking-wider text-[#6e6584]"
                    )
                    ui.label(state.tome_title).classes(
                        "text-sm text-[#eceaf4] truncate mt-1"
                    )
                    if state.active_tome_id:
                        ui.label(state.active_tome_id[:8]).classes(
                            "text-[10px] text-[#6e6584] font-mono mt-0.5"
                        )

            # Recent Sessions
            with ui.column().classes("mt-4 flex-1 min-h-0 overflow-y-auto px-2 w-full"):
                ui.label("Recent Sessions").classes(
                    "text-[10px] font-semibold uppercase tracking-wider "
                    "text-[#6e6584] px-2 py-1"
                )
                if not state.loaded_tomes:
                    ui.label("No sessions yet").classes(
                        "text-[11px] text-[#6e6584] px-2 py-2"
                    )
                else:
                    for entry in state.loaded_tomes:
                        bg = (
                            "bg-[#0e0e12]/70 border border-[#292335]/60"
                            if entry.is_active
                            else "hover:bg-[#0e0e12]/40"
                        )
                        with (
                            ui.row()
                            .classes(
                                f"w-full items-center px-2 py-1.5 rounded-md "
                                f"cursor-pointer text-xs {bg} no-wrap"
                            )
                            .on(
                                "click",
                                lambda _, e=entry: state.switch_to_tome(e.tome_id),
                            )
                        ):
                            ui.icon("chat_bubble_outline", size="12px").classes(
                                "text-[#9c94b3] shrink-0"
                            )
                            ui.label(entry.title).classes(
                                "text-[#eceaf4] truncate text-[11px] flex-1"
                            )
                            with ui.row().classes("items-center gap-1 shrink-0"):
                                ui.label(entry.relative_time).classes(
                                    "text-[10px] text-[#6e6584]"
                                )
                                if entry.git_branch:
                                    ui.label(entry.git_branch).classes(
                                        "text-[10px] px-1 py-0.5 rounded "
                                        "bg-[#7b6cf6]/10 text-[#7b6cf6] "
                                        "border border-[#7b6cf6]/30 font-mono"
                                    )
        else:
            ui.element("div").classes("flex-1")

        # Bottom: version
        if collapsed:
            with ui.row().classes(
                "w-full border-t border-[#292335] py-2 "
                "justify-center items-center shrink-0"
            ):
                ui.label(f"v{__version__}").classes("text-[9px] text-[#6e6584]")
        else:
            with ui.row().classes(
                "w-full border-t border-[#292335] px-3 py-2 items-center "
                "justify-end shrink-0 no-wrap"
            ):
                ui.label(f"v{__version__}").classes("text-[10px] text-[#6e6584]")

    return container


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
        else "text-[#9c94b3] hover:text-[#eceaf4] hover:bg-[#0e0e12]/60"
    )
    if collapsed:
        with (
            ui.row()
            .classes(
                f"w-full justify-center py-2 rounded-md "
                f"cursor-pointer transition-colors {active_cls}"
            )
            .on("click", lambda _, v=view: state.set_current_view(v))
        ):
            ui.icon(icon, size="16px").classes(
                "shrink-0 " + ("nav-icon-active" if active else "text-[#9c94b3]")
            )
            sidebar_hint(label)
    else:
        with (
            ui.row()
            .classes(
                f"w-full items-center gap-2.5 px-3 py-2 rounded-md "
                f"cursor-pointer text-xs transition-colors {active_cls} no-wrap"
            )
            .on("click", lambda _, v=view: state.set_current_view(v))
        ):
            ui.icon(icon, size="14px").classes(
                "shrink-0 " + ("nav-icon-active" if active else "text-[#9c94b3]")
            )
            ui.label(label).classes("font-normal truncate flex-1")
