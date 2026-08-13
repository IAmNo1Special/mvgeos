"""Left navigation sidebar component for Antigravity shell."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_sidebar(state: AppState) -> ui.column:
    """Render the collapsible left navigation sidebar."""
    container = ui.column().classes(
        "h-full bg-[#13151b] border-r border-[#252936] p-3 "
        "flex flex-col justify-between transition-all duration-200"
    )
    if not state.sidebar_expanded:
        container.classes("w-14 items-center", remove="w-64")
    else:
        container.classes("w-64", remove="w-14 items-center")

    with container:
        # Top section
        with ui.column().classes("w-full gap-3"):
            # Header with App Title and Toggle Button
            with ui.row().classes("w-full items-center justify-between"):
                if state.sidebar_expanded:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("auto_awesome", size="20px").classes("text-[#3b82f6]")
                        ui.label("Antigravity").classes(
                            "text-sm font-semibold text-[#e6edf3] tracking-wide"
                        )
                ui.button(
                    icon="view_sidebar" if state.sidebar_expanded else "menu",
                    on_click=state.toggle_sidebar,
                ).props("flat dense round text-color=grey-5").mark("toggle_sidebar_btn")

            # New Conversation Button
            if state.sidebar_expanded:
                ui.button(
                    "+ New Conversation",
                    on_click=state.new_conversation,
                ).props("unelevated no-caps").classes(
                    "w-full bg-[#1b1e27] hover:bg-[#222632] text-[#e6edf3] "
                    "border border-[#252936] text-xs font-medium py-2 rounded-lg"
                ).mark("new_conversation_btn")
            else:
                ui.button(
                    icon="add",
                    on_click=state.new_conversation,
                ).props("flat dense round text-color=grey-4").mark(
                    "new_conversation_btn"
                )

            # Tomes / Conversation List Area
            with ui.column().classes("w-full gap-1 mt-2"):
                if state.sidebar_expanded:
                    ui.label("Recent Tomes").classes(
                        "text-[10px] font-semibold uppercase tracking-wider "
                        "text-[#64748b] px-2"
                    )
                    # Active tome or placeholder indicator
                    with ui.row().classes(
                        "w-full items-center gap-2 px-2 py-1.5 rounded "
                        "bg-[#1b1e27]/50 border border-[#252936]/40 cursor-pointer"
                    ):
                        ui.icon("chat_bubble_outline", size="14px").classes(
                            "text-[#8b949e]"
                        )
                        ui.label(state.tome_title).classes(
                            "text-xs text-[#e6edf3] truncate"
                        )

        # Bottom section
        with ui.column().classes("w-full border-t border-[#252936] pt-3 gap-2"):
            if state.sidebar_expanded:
                with ui.row().classes(
                    "w-full items-center justify-between px-2 text-[#8b949e] "
                    "hover:text-[#e6edf3] cursor-pointer"
                ):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("settings", size="18px")
                        ui.label("Settings").classes("text-xs font-medium")
                    ui.label("v0.1.0").classes("text-[10px] text-[#64748b]")
            else:
                ui.button(icon="settings").props("flat dense round text-color=grey-5")

    return container
