"""Active conversation view component shown when a Tome is loaded."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_conversation_view(state: AppState) -> ui.column:
    """Render the active conversation view when a Tome is loaded."""
    container = ui.column().classes(
        "w-full h-full items-center justify-center gap-6 px-6 text-center select-none"
    )

    with container:
        with ui.column().classes("items-center gap-2 mb-2"):
            with ui.row().classes(
                "w-12 h-12 rounded-2xl bg-[#1e212b] border border-[#2b2f3d] "
                "items-center justify-center shadow-lg"
            ):
                ui.icon("chat_bubble", size="24px").classes("text-[#3b82f6]")
            ui.label(state.tome_title).classes(
                "text-xl font-semibold text-[#e6edf3] tracking-tight"
            )
            if state.active_tome_id:
                ui.label(state.active_tome_id[:8]).classes(
                    "text-[10px] text-[#64748b] font-mono"
                )

        ui.label("Active session loaded from Tome").classes("text-xs text-[#8b949e]")

        ui.label(f"{len(state.loaded_tomes)} tome(s) indexed for this project").classes(
            "text-[10px] text-[#64748b]"
        )

    return container
