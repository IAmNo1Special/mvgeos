"""Top navigation and workspace header bar component."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_header(state: AppState) -> ui.row:
    """Render the top navigation header with breadcrumbs and actions."""
    project_name = state.project_path.name or str(state.project_path)

    header = ui.row().classes(
        "w-full h-11 bg-[#13151b] border-b border-[#2b2f3d] px-4 "
        "items-center justify-between z-10 shrink-0 select-none"
    )

    with header:
        # Left Breadcrumbs and Navigation Icons
        with ui.row().classes("items-center gap-3 text-xs"):
            with ui.row().classes("items-center gap-1 text-[#8b949e]"):
                ui.icon("view_sidebar", size="16px").classes(
                    "hover:text-[#e6edf3] cursor-pointer"
                ).on("click", state.toggle_sidebar)
                ui.icon("arrow_back", size="15px").classes(
                    "cursor-not-allowed opacity-40"
                )
                ui.icon("arrow_forward", size="15px").classes(
                    "cursor-not-allowed opacity-40"
                )

            with ui.row().classes("items-center gap-1.5 ml-1"):
                ui.icon("folder_open", size="15px").classes("text-[#3b82f6]")
                ui.label(project_name).classes("font-medium text-[#e6edf3]")
                if state.active_tome_id is not None:
                    ui.label("/").classes("text-[#64748b]")
                    ui.label(state.tome_title).classes("text-[#8b949e] font-normal")

        # Right Action Buttons
        with ui.row().classes("items-center gap-2"):
            # Open IDE Button
            with (
                ui.button("Open IDE", icon="terminal")
                .props("unelevated dense no-caps")
                .classes(
                    "bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] border "
                    "border-[#2b2f3d] text-xs px-2.5 py-1 rounded-md"
                )
                .on("click", state.open_in_editor)
                .mark("open_ide_btn")
            ):
                ui.tooltip("Launch external editor in workspace")

            # 3-Dots Action Menu
            with (
                ui.button(icon="more_vert")
                .props("flat dense round text-color=grey-5")
                .mark("action_menu_btn"),
                ui.menu().classes(
                    "bg-[#1e212b] border border-[#2b2f3d] text-[#e6edf3]"
                ),
            ):
                ui.menu_item(
                    "Export Transcript",
                    on_click=lambda: state.export_tome(),
                ).mark("export_transcript_btn")
                ui.menu_item(
                    "Fork Tome",
                    on_click=lambda: state.fork_tome(),
                ).mark("fork_tome_btn")
                ui.separator().classes("bg-[#2b2f3d]")
                ui.menu_item(
                    "Clear Conversation",
                    on_click=state.clear_history,
                ).mark("clear_conversation_btn")

            # Inspector Panel Toggle Button
            ui.button(
                icon="dock" if state.inspector_expanded else "view_sidebar",
                on_click=state.toggle_inspector,
            ).props("flat dense round text-color=grey-5").mark("toggle_inspector_btn")

    return header
