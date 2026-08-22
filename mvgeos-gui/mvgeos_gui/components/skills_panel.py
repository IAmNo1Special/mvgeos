"""Skills panel: browse available runes/skills."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_skills_panel(state: AppState) -> None:
    """Render the skills browser view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Skills").classes("text-2xl font-semibold text-[#e6edf3]")

        skills = state.active_skills
        if not skills:
            ui.label("No skills loaded").classes("text-xs text-[#64748b] mt-4")
        else:
            for skill in skills:
                with ui.card().classes(
                    "w-full p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-lg"
                ):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(skill.name).classes(
                            "text-sm font-semibold text-[#e6edf3]"
                        )
                        if skill.invoked:
                            ui.badge("Invoked", color="green").props(
                                "rounded dense"
                            ).classes("text-[10px]")
                    ui.label(skill.description or "No description").classes(
                        "text-xs text-[#8b949e] mt-1"
                    )
                    ui.label(skill.scope).classes(
                        "text-[10px] text-[#64748b] mt-1 font-mono"
                    )

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("bg-[#3b82f6] text-white")
