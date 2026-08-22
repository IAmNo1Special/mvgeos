"""Timeline panel: agent activity and session lineage."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_timeline_panel(state: AppState) -> None:
    """Render the timeline view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Timeline").classes("text-2xl font-semibold text-[#e6edf3]")

        with ui.card().classes(
            "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
        ):
            ui.label("Activity").classes("text-sm font-semibold text-[#e6edf3] mb-3")
            ui.label("No recent activity").classes("text-xs text-[#64748b]")

        with ui.card().classes(
            "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
        ):
            ui.label("Session Lineage").classes(
                "text-sm font-semibold text-[#e6edf3] mb-3"
            )
            ui.label("No forked sessions yet").classes("text-xs text-[#64748b]")

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("bg-[#3b82f6] text-white")
