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
            "w-16 h-16 rounded-3xl bg-[#0e0e12] border border-[#292335] "
            "items-center justify-center shadow-lg mb-6"
        ):
            ui.icon("auto_awesome", size="32px").classes("text-[#7b6cf6]")

        ui.label("Welcome to MvgeOS").classes(
            "text-3xl font-semibold text-[#eceaf4] tracking-tight"
        )
        ui.label("Your AI coding agent desktop.").classes(
            "text-sm text-[#9c94b3] mt-1 mb-8"
        )

        # Project card
        with (
            ui.card().classes(
                "w-full max-w-xl p-4 bg-[#0e0e12] border "
                "border-[#292335] rounded-xl mb-6"
            ),
            ui.row().classes("w-full items-center justify-between"),
        ):
            with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                ui.icon("folder_open", size="18px").classes("text-[#7b6cf6] shrink-0")
                project_name = state.project_path.name or str(state.project_path)
                ui.label(project_name).classes(
                    "text-sm text-[#eceaf4] truncate font-medium"
                )
            with ui.row().classes("items-center gap-1"):
                ui.button(
                    icon="settings",
                    on_click=state.open_workspace_settings,
                ).props("flat dense round text-color=grey-5 size=xs")

        # Quick actions
        with ui.row().classes("gap-3 flex-wrap justify-center mb-8"):
            ui.button(
                "New Conversation",
                icon="add",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated no-caps").classes(
                "bg-[#0e0e12] hover:bg-[#16161d] text-[#eceaf4] border "
                "border-[#292335] text-xs px-4 py-2 rounded-lg"
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
                "w-full max-w-xl mt-8 p-4 bg-[#0e0e12] border "
                "border-[#292335] rounded-xl text-left"
            ):
                ui.label("Recent Sessions").classes(
                    "text-xs font-semibold text-[#9c94b3] uppercase tracking-wider mb-3"
                )
                for entry in state.loaded_tomes[:5]:
                    with (
                        ui.row()
                        .classes(
                            "w-full items-center gap-2 px-2 py-1.5 rounded-md "
                            "hover:bg-[#16161d] cursor-pointer text-xs"
                        )
                        .on("click", lambda e=entry: state.switch_to_tome(e.tome_id))
                    ):
                        ui.icon("chat_bubble_outline", size="13px").classes(
                            "text-[#9c94b3]"
                        )
                        ui.label(entry.title).classes("text-[#eceaf4] truncate flex-1")
                        ui.label(entry.relative_time).classes("text-[#6e6584] shrink-0")


def _stat_card(label: str, value: str) -> None:
    with ui.card().classes(
        "flex-1 min-w-[120px] p-4 bg-[#0e0e12] border border-[#292335] rounded-xl"
    ):
        ui.label(value).classes("text-lg font-semibold text-[#eceaf4]")
        ui.label(label).classes(
            "text-[10px] text-[#6e6584] uppercase tracking-wider mt-1"
        )
