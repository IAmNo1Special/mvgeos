"""Terminal overlay panel with ANSI color support."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_terminal_panel(state: AppState) -> None:
    """Render the terminal overlay panel."""
    if not state.terminal_open:
        return

    with (
        ui.row().classes("w-full shrink-0 border-t border-[#292335] bg-[#050506]"),
        ui.column().classes("w-full h-48 overflow-y-auto p-3 font-mono text-xs"),
    ):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label("Terminal").classes(
                "text-[10px] font-semibold text-[#9c94b3] uppercase tracking-wider"
            )
            ui.button(
                icon="close",
                on_click=state.toggle_terminal,
            ).props("flat dense round text-color=grey-5 size=xs")

        ui.label("Terminal output will appear here.").classes("text-xs text-[#6e6584]")
        ui.label("$").classes("text-xs text-[#22c55e]")
