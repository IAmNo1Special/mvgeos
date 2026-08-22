"""Application settings panel."""

from nicegui import ui

from mvgeos_gui.model_catalog import get_model_options
from mvgeos_gui.state import AppState


def render_settings_panel(state: AppState) -> None:
    """Render the full settings view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-6"):
        ui.label("Settings").classes("text-2xl font-semibold text-[#e6edf3]")

        # Behavior
        with ui.card().classes(
            "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
        ):
            ui.label("Behavior").classes("text-sm font-semibold text-[#e6edf3] mb-3")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Default model").classes("text-xs text-[#8b949e]")
                ui.select(
                    options=get_model_options(),
                    value=state.selected_model,
                    on_change=lambda e: state.switch_model(e.value),
                    with_input=True,
                ).props("dense dark outlined rounded").classes("text-xs")

        # Appearance
        with ui.card().classes(
            "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
        ):
            ui.label("Appearance").classes("text-sm font-semibold text-[#e6edf3] mb-3")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Theme").classes("text-xs text-[#8b949e]")
                ui.select(
                    options=["Dark", "Light", "System"],
                    value="Dark",
                ).props("dense dark outlined rounded").classes("text-xs")

        # About
        with ui.card().classes(
            "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
        ):
            ui.label("About").classes("text-sm font-semibold text-[#e6edf3] mb-3")
            ui.label("MvgeOS v0.1.0").classes("text-xs text-[#8b949e]")
            ui.label("A Python-based AI coding agent desktop GUI.").classes(
                "text-xs text-[#64748b] mt-1"
            )

        # Back button
        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("bg-[#3b82f6] text-white")
