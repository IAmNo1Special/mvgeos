"""Terminal overlay panel with ANSI color support."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_terminal_panel(state: AppState) -> None:
    """Render the terminal overlay panel."""
    if not state.terminal_open:
        return

    with (
        ui.row().classes("w-full shrink-0 border-t border-[#2b2f3d] bg-[#0d0f14]"),
        ui.column().classes("w-full h-48 overflow-y-auto p-3 font-mono text-xs"),
    ):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label("Terminal").classes(
                "text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider"
            )
            ui.button(
                icon="close",
                on_click=state.toggle_terminal,
            ).props("flat dense round text-color=grey-5 size=xs")

        ui.label("Terminal output will appear here.").classes("text-xs text-[#64748b]")
        ui.label("$").classes("text-xs text-[#22c55e]")
