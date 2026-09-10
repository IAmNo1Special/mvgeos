"""Notes panel: saved prompts and commands."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_notes_panel(state: AppState) -> None:
    """Render the notes/prompts view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Notes").classes("text-2xl font-semibold text-[#eceaf4]")

        ui.input(
            placeholder="Search notes...",
        ).props("dense dark outlined rounded").classes("w-full text-xs")

        ui.label("No saved notes yet").classes("text-xs text-[#6e6584] mt-4")

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("mvge-glow-btn text-white")
