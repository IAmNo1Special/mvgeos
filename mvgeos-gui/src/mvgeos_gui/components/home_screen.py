"""Home dashboard: greeting, project picker, recent sessions, quick actions, stats."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_home_screen(state: AppState) -> None:
    """Render the full-screen home dashboard."""
    with ui.column().classes(
        "w-full h-full overflow-y-auto items-center px-6 py-10 text-center select-none"
    ):
        # App emblem
        with ui.row().classes(
            "w-16 h-16 rounded-3xl bg-[#1e212b] border border-[#2b2f3d] "
            "items-center justify-center shadow-lg mb-6"
        ):
            ui.icon("auto_awesome", size="32px").classes("text-[#3b82f6]")

        ui.label("Welcome to MvgeOS").classes(
            "text-3xl font-semibold text-[#e6edf3] tracking-tight"
        )
        ui.label("Your AI coding agent desktop.").classes(
            "text-sm text-[#8b949e] mt-1 mb-8"
        )

        # Project card
        with (
            ui.card().classes(
                "w-full max-w-xl p-4 bg-[#1e212b] border "
                "border-[#2b2f3d] rounded-xl mb-6"
            ),
            ui.row().classes("w-full items-center justify-between"),
        ):
            with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                ui.icon("folder_open", size="18px").classes("text-[#3b82f6] shrink-0")
                project_name = state.project_path.name or str(state.project_path)
                ui.label(project_name).classes(
                    "text-sm text-[#e6edf3] truncate font-medium"
                )
            with ui.row().classes("items-center gap-1"):
                ui.button(
                    icon="settings",
                    on_click=state.open_workspace_settings,
                ).props("flat dense round text-color=grey-5 size=xs")
                ui.button(
                    icon="edit",
                    on_click=lambda: ui.notify("Project editing not yet implemented"),
                ).props("flat dense round text-color=grey-5 size=xs")

        # Quick actions
        with ui.row().classes("gap-3 flex-wrap justify-center mb-8"):
            ui.button(
                "New Conversation",
                icon="add",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated no-caps").classes(
                "bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] border "
                "border-[#2b2f3d] text-xs px-4 py-2 rounded-lg"
            )
            ui.button(
                "Open Project",
                icon="folder_open",
                on_click=lambda: ui.notify("Project picker not yet implemented"),
            ).props("unelevated no-caps").classes(
                "bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] border "
                "border-[#2b2f3d] text-xs px-4 py-2 rounded-lg"
            )
            ui.button(
                "Quick Start",
                icon="bolt",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated no-caps").classes(
                "bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] border "
                "border-[#2b2f3d] text-xs px-4 py-2 rounded-lg"
            )

        # Stats
        with ui.row().classes("gap-4 flex-wrap justify-center w-full max-w-3xl"):
            _stat_card("Sessions", str(len(state.loaded_tomes)))
            _stat_card("Mana Used", f"{state.total_mana_used:,}")
            _stat_card("Model", state.selected_model.split("/")[-1].split(":")[0])
            _stat_card("Status", state.mvge_status.title())

        # Recent sessions
        if state.loaded_tomes:
            with ui.card().classes(
                "w-full max-w-xl mt-8 p-4 bg-[#1e212b] border "
                "border-[#2b2f3d] rounded-xl text-left"
            ):
                ui.label("Recent Sessions").classes(
                    "text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-3"
                )
                for entry in state.loaded_tomes[:5]:
                    with (
                        ui.row()
                        .classes(
                            "w-full items-center gap-2 px-2 py-1.5 rounded-md "
                            "hover:bg-[#262a36] cursor-pointer text-xs"
                        )
                        .on("click", lambda e=entry: state.switch_to_tome(e.tome_id))
                    ):
                        ui.icon("chat_bubble_outline", size="13px").classes(
                            "text-[#8b949e]"
                        )
                        ui.label(entry.title).classes("text-[#e6edf3] truncate flex-1")
                        ui.label(entry.relative_time).classes("text-[#64748b] shrink-0")


def _stat_card(label: str, value: str) -> None:
    with ui.card().classes(
        "flex-1 min-w-[120px] p-4 bg-[#1e212b] border border-[#2b2f3d] rounded-xl"
    ):
        ui.label(value).classes("text-lg font-semibold text-[#e6edf3]")
        ui.label(label).classes(
            "text-[10px] text-[#64748b] uppercase tracking-wider mt-1"
        )
