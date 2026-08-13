"""Right context inspector panel component with collapsible accordions."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_inspector(state: AppState) -> ui.column:
    """Render the collapsible right context inspector panel."""
    container = ui.column().classes(
        "h-full bg-[#13151b] border-l border-[#252936] p-0 "
        "flex flex-col justify-between transition-all duration-200"
    )
    if not state.inspector_expanded:
        container.classes("w-0 p-0 hidden overflow-hidden", remove="w-80")
        return container

    container.classes("w-80", remove="w-0 p-0 hidden overflow-hidden")

    with container:
        # Header
        with ui.row().classes(
            "w-full h-12 px-4 items-center justify-between "
            "border-b border-[#252936] shrink-0"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("layers", size="18px").classes("text-[#3b82f6]")
                ui.label("Context").classes("text-xs font-semibold text-[#e6edf3]")

            ui.button(
                icon="close",
                on_click=state.toggle_inspector,
            ).props("flat dense round text-color=grey-5 size=sm").mark(
                "toggle_inspector_btn"
            )

        # Scrollable Accordions list
        with ui.scroll_area().classes("w-full flex-grow p-2 gap-1"):
            # 1. Subagents
            with (
                ui.expansion("Subagents", icon="hub").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#252936]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No active subagents").classes("italic text-[11px]")

            # 2. Files Changed
            with (
                ui.expansion("Files Changed", icon="difference").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#252936]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("Working tree clean").classes("italic text-[11px]")

            # 3. Artifacts
            with (
                ui.expansion("Artifacts", icon="description").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#252936]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No artifacts generated").classes("italic text-[11px]")

            # 4. Skills Used
            with (
                ui.expansion("Skills Used", icon="auto_stories").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#252936]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No skills invoked in session").classes("italic text-[11px]")

            # 5. Uploads
            with (
                ui.expansion("Uploads", icon="cloud_upload").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#252936]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No uploaded files").classes("italic text-[11px]")

            # 6. Background Tasks
            with (
                ui.expansion("Background Tasks", icon="schedule").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#252936]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No running background tasks").classes("italic text-[11px]")

    return container
