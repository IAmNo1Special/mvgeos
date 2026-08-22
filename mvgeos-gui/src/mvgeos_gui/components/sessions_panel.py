"""Sessions panel: search, filter, tags, archive/delete."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_sessions_panel(state: AppState) -> None:
    """Render the sessions management view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Sessions").classes("text-2xl font-semibold text-[#e6edf3]")
            ui.button(
                "New Session",
                on_click=state.new_conversation,
            ).props("unelevated").classes("bg-[#3b82f6] text-white")

        ui.input(
            placeholder="Search sessions...",
        ).props("dense dark outlined rounded").classes("w-full text-xs")

        if not state.loaded_tomes:
            ui.label("No sessions yet").classes("text-xs text-[#64748b] mt-4")
        else:
            for entry in state.loaded_tomes:
                with (
                    ui.card()
                    .classes(
                        "w-full p-3 bg-[#1e212b] border border-[#2b2f3d] "
                        "rounded-lg cursor-pointer hover:border-[#3b82f6] "
                        "transition-colors"
                    )
                    .on("click", lambda e=entry: state.switch_to_tome(e.tome_id))
                ):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                            ui.icon("chat_bubble_outline", size="16px").classes(
                                "text-[#8b949e] shrink-0"
                            )
                            ui.label(entry.title).classes(
                                "text-sm text-[#e6edf3] truncate"
                            )
                        with ui.row().classes("items-center gap-2 shrink-0"):
                            ui.label(entry.relative_time).classes(
                                "text-[10px] text-[#64748b]"
                            )
                            if entry.git_branch:
                                ui.label(entry.git_branch).classes(
                                    "text-[10px] px-1 py-0.5 rounded "
                                    "bg-[#3b82f6]/10 text-[#3b82f6] "
                                    "border border-[#3b82f6]/30 font-mono"
                                )
                    if entry.is_active:
                        ui.label("Active").classes("text-[10px] text-[#3b82f6] mt-1")

        # Back button
        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("bg-[#3b82f6] text-white")
