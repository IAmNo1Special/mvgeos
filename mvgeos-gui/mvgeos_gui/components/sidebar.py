"""Left navigation sidebar component for MvgeOS shell."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_sidebar(state: AppState) -> ui.column:
    """Render the collapsible left navigation sidebar."""
    container = ui.column().classes(
        "h-full bg-[#13151b] border-r border-[#2b2f3d] p-3 pb-6 "
        "flex flex-col justify-between transition-all duration-200 shrink-0 select-none"
    )
    if not state.sidebar_expanded:
        container.classes("w-14 items-center", remove="w-64")
    else:
        container.classes("w-64", remove="w-14 items-center")

    with container:
        # Top section
        with ui.column().classes("w-full gap-2.5"):
            # Header with App Title and Toggle Button
            with ui.row().classes("w-full items-center justify-between pb-1"):
                if state.sidebar_expanded:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("auto_awesome", size="18px").classes("text-[#3b82f6]")
                        ui.label("MvgeOS").classes(
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
                    "w-full bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] "
                    "border border-[#2b2f3d] text-xs font-medium py-2 "
                    "rounded-lg text-left pl-3"
                ).mark("new_conversation_btn")
            else:
                ui.button(
                    icon="add",
                    on_click=state.new_conversation,
                ).props("flat dense round text-color=grey-4").mark(
                    "new_conversation_btn"
                )

            # Sidebar Menu Links (Image 1 reference)
            if state.sidebar_expanded:
                with ui.column().classes("w-full gap-0.5 pt-1"):
                    with ui.row().classes(
                        "w-full items-center gap-2.5 px-2 py-1.5 rounded-md "
                        "text-[#8b949e] hover:text-[#e6edf3] "
                        "hover:bg-[#1e212b]/60 cursor-pointer text-xs"
                    ):
                        ui.icon("history", size="16px")
                        ui.label("Conversation History").classes("font-normal")

                    with ui.row().classes(
                        "w-full items-center gap-2.5 px-2 py-1.5 rounded-md "
                        "text-[#8b949e] hover:text-[#e6edf3] "
                        "hover:bg-[#1e212b]/60 cursor-pointer text-xs"
                    ):
                        ui.icon("schedule", size="16px")
                        ui.label("Scheduled Tasks").classes("font-normal")

            # Projects & Tomes Area
            with ui.column().classes("w-full gap-1 mt-2"):
                if state.sidebar_expanded:
                    with ui.row().classes(
                        "w-full items-center justify-between px-2 pt-1"
                    ):
                        ui.label("Projects").classes(
                            "text-[10px] font-semibold uppercase "
                            "tracking-wider text-[#64748b]"
                        )
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("filter_list", size="14px").classes(
                                "text-[#64748b]"
                            )
                            ui.icon("create_new_folder", size="14px").classes(
                                "text-[#64748b]"
                            )

                    # Project Folder Tree node
                    project_name = state.project_path.name or str(state.project_path)
                    with ui.row().classes(
                        "w-full items-center gap-1.5 px-2 py-1 text-xs "
                        "text-[#e6edf3] font-medium"
                    ):
                        ui.icon("folder_open", size="15px").classes("text-[#3b82f6]")
                        ui.label(project_name).classes("truncate")

                    # Active Tome row
                    with ui.row().classes(
                        "w-full items-center justify-between pl-6 pr-2 py-1.5 "
                        "rounded-md bg-[#1e212b]/70 border border-[#2b2f3d]/60 "
                        "cursor-pointer text-xs"
                    ):
                        with ui.row().classes(
                            "items-center gap-1.5 truncate max-w-[150px]"
                        ):
                            ui.icon("chat_bubble_outline", size="13px").classes(
                                "text-[#8b949e]"
                            )
                            ui.label(state.tome_title).classes(
                                "text-[#e6edf3] truncate text-[11px]"
                            )
                        ui.label("now").classes("text-[10px] text-[#64748b]")

        # Bottom section with generous bottom padding
        with ui.column().classes("w-full border-t border-[#2b2f3d] pt-3 pb-2 gap-2"):
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
