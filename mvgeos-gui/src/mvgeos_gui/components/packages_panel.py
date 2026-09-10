"""Packages panel: installed packages and catalog."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_packages_panel(state: AppState) -> None:
    """Render the packages view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Packages").classes("text-2xl font-semibold text-[#eceaf4]")

        ui.input(
            placeholder="Search packages...",
        ).props("dense dark outlined rounded").classes("w-full text-xs")

        with ui.card().classes(
            "w-full p-4 bg-[#0e0e12] border border-[#292335] rounded-xl"
        ):
            ui.label("Installed").classes("text-sm font-semibold text-[#eceaf4] mb-3")
            ui.label("No packages installed").classes("text-xs text-[#6e6584]")

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("mvge-glow-btn text-white")
