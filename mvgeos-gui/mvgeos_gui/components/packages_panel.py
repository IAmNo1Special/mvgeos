"""Packages panel: installed packages and catalog."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_packages_panel(state: AppState) -> None:
    """Render the packages view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Packages").classes("text-2xl font-semibold text-[#e6edf3]")

        ui.input(
            placeholder="Search packages...",
        ).props("dense dark outlined rounded").classes("w-full text-xs")

        with ui.card().classes(
            "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
        ):
            ui.label("Installed").classes("text-sm font-semibold text-[#e6edf3] mb-3")
            ui.label("No packages installed").classes("text-xs text-[#64748b]")

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("bg-[#3b82f6] text-white")
