"""Top navigation and workspace header bar component."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_header(state: AppState) -> ui.row:
    """Render the top navigation header with breadcrumbs and actions."""
    project_name = state.project_path.name or str(state.project_path)

    header = ui.row().classes(
        "w-full h-12 bg-[#0e1117] border-b border-[#252936] px-4 "
        "items-center justify-between z-10 shrink-0"
    )

    with header:
        # Left Breadcrumbs: <project> / <tome_title>
        with ui.row().classes("items-center gap-2 text-xs"):
            ui.icon("folder_open", size="16px").classes("text-[#3b82f6]")
            ui.label(project_name).classes("font-semibold text-[#e6edf3]")
            ui.label("/").classes("text-[#64748b]")
            ui.label(state.tome_title).classes("text-[#8b949e] font-medium")

        # Right Action Buttons
        with ui.row().classes("items-center gap-2"):
            # Open IDE Button
            with (
                ui.button(
                    "Open IDE",
                    icon="terminal",
                )
                .props("unelevated dense no-caps")
                .classes(
                    "bg-[#1b1e27] hover:bg-[#222632] text-[#e6edf3] border "
                    "border-[#252936] text-xs px-2 py-1 rounded"
                )
            ):
                ui.tooltip("Launch external editor in workspace")

            # 3-Dots Action Menu
            with (
                ui.button(icon="more_vert").props("flat dense round text-color=grey-5"),
                ui.menu().classes(
                    "bg-[#1b1e27] border border-[#252936] text-[#e6edf3]"
                ),
            ):
                ui.menu_item(
                    "Export Transcript",
                    on_click=lambda: ui.notify("Exported transcript"),
                )
                ui.menu_item(
                    "Fork Tome",
                    on_click=lambda: ui.notify("Forked tome"),
                )
                ui.separator().classes("bg-[#252936]")
                ui.menu_item(
                    "Clear Conversation",
                    on_click=state.new_conversation,
                )

            # Inspector Panel Toggle Button
            ui.button(
                icon="dock" if state.inspector_expanded else "view_sidebar",
                on_click=state.toggle_inspector,
            ).props("flat dense round text-color=grey-5").mark("toggle_inspector_btn")

    return header
