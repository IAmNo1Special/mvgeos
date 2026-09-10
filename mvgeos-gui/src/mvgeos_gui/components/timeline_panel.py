"""Timeline panel: agent activity and session lineage."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_timeline_panel(state: AppState) -> None:
    """Render the timeline view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Timeline").classes("text-2xl font-semibold text-[#eceaf4]")

        with ui.card().classes(
            "w-full p-4 bg-[#0e0e12] border border-[#292335] rounded-xl"
        ):
            ui.label("Activity").classes("text-sm font-semibold text-[#eceaf4] mb-3")
            ui.label("No recent activity").classes("text-xs text-[#6e6584]")

        with ui.card().classes(
            "w-full p-4 bg-[#0e0e12] border border-[#292335] rounded-xl"
        ):
            ui.label("Session Lineage").classes(
                "text-sm font-semibold text-[#eceaf4] mb-3"
            )
            ui.label("No forked sessions yet").classes("text-xs text-[#6e6584]")

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("mvge-glow-btn text-white")
