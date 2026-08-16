"""Centered empty state view with workspace project picker dropdown."""

from pathlib import Path

from nicegui import ui

from mvgeos_gui.state import AppState


def render_empty_state(state: AppState) -> ui.column:
    """Render centered empty state with project switcher dropdown."""
    container = ui.column().classes(
        "w-full h-full items-center justify-center gap-4 px-6 text-center select-none"
    )

    with container:
        # App Emblem & Greeting
        with ui.column().classes("items-center gap-2 mb-2"):
            with ui.row().classes(
                "w-12 h-12 rounded-2xl bg-[#1e212b] border border-[#2b2f3d] "
                "items-center justify-center shadow-lg"
            ):
                ui.icon("auto_awesome", size="24px").classes("text-[#3b82f6]")
            ui.label("How can MvgeOS help you today?").classes(
                "text-xl font-semibold text-[#e6edf3] tracking-tight"
            )
            ui.label(
                "Summon an AI coding agent to inspect, code, and execute spells."
            ).classes("text-xs text-[#8b949e]")

        # Centered Active Workspace Selector Pill
        with ui.row().classes("items-center justify-center gap-2"):
            project_name = state.project_path.name or str(state.project_path)
            with ui.button().classes(
                "bg-[#1e212b] hover:bg-[#262a36] border border-[#2b2f3d] "
                "text-[#e6edf3] text-xs py-1.5 px-3 rounded-lg normal-case shadow-sm"
            ):
                with ui.row().classes("items-center gap-1.5"):
                    ui.icon("folder", size="15px").classes("text-[#3b82f6]")
                    ui.label(project_name).classes("font-medium max-w-[200px] truncate")
                    ui.icon("expand_more", size="15px").classes("text-[#8b949e]")

                ui.button(
                    icon="settings",
                    on_click=state.open_workspace_settings,
                ).props("flat dense round text-color=grey-5 size=xs").mark(
                    "workspace_settings_btn"
                )

                # Dropdown Menu
                with ui.menu().classes(
                    "w-80 bg-[#13151b] border border-[#2b2f3d] p-2 "
                    "text-[#e6edf3] shadow-2xl"
                ):
                    ui.input(placeholder="Search projects...").props(
                        "dense outlined dark rounded"
                    ).classes("w-full mb-2 text-xs")

                    ui.label("Recent Projects").classes(
                        "text-[10px] uppercase font-bold text-[#64748b] px-2 py-1"
                    )
                    with ui.column().classes("w-full gap-0.5"):
                        for proj in state.recent_projects:
                            with (
                                ui.row()
                                .classes(
                                    "w-full items-center justify-between px-2 py-1.5 "
                                    "rounded hover:bg-[#1e212b] cursor-pointer text-xs"
                                )
                                .on("click", lambda _, p=proj: state.set_project(p)),
                                ui.row().classes("items-center gap-2 truncate"),
                            ):
                                ui.icon("folder_open", size="14px").classes(
                                    "text-[#8b949e]"
                                )
                                ui.label(proj.name or str(proj)).classes("truncate")

                    ui.separator().classes("bg-[#2b2f3d] my-2")

                    # Quick actions in project picker
                    with ui.column().classes("w-full gap-0.5"):
                        with (
                            ui.row()
                            .classes(
                                "w-full items-center gap-2 px-2 py-1.5 rounded "
                                "hover:bg-[#1e212b] cursor-pointer text-xs"
                            )
                            .on(
                                "click",
                                lambda: ui.notify("Select folder to create project"),
                            ),
                        ):
                            ui.icon("add_circle_outline", size="14px").classes(
                                "text-[#22c55e]"
                            )
                            ui.label("New Project").classes("font-medium")

                        with (
                            ui.row()
                            .classes(
                                "w-full items-center gap-2 px-2 py-1.5 rounded "
                                "hover:bg-[#1e212b] cursor-pointer text-xs"
                            )
                            .on("click", lambda: ui.notify("Quick Start loaded")),
                        ):
                            ui.icon("bolt", size="14px").classes("text-[#eab308]")
                            ui.label("Quick Start").classes("font-medium")

                        with (
                            ui.row()
                            .classes(
                                "w-full items-center gap-2 px-2 py-1.5 rounded "
                                "hover:bg-[#1e212b] cursor-pointer text-xs"
                            )
                            .on(
                                "click",
                                lambda: state.set_project(
                                    Path.home() / ".agents" / ".mvgeos" / "sandbox"
                                ),
                            ),
                        ):
                            ui.icon("close", size="14px").classes("text-[#8b949e]")
                            ui.label("No Project").classes("text-[#8b949e]")

        # Quick action pills
        with ui.row().classes("gap-2 items-center justify-center pt-1"):
            ui.button(
                "New Project",
                icon="add",
                on_click=lambda: ui.notify("New Project"),
            ).props("unelevated dense no-caps").classes(
                "bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] border "
                "border-[#2b2f3d] text-xs px-3 py-1.5 rounded-lg"
            )

            ui.button(
                "Quick Start",
                icon="bolt",
                on_click=lambda: ui.notify("Quick Start"),
            ).props("unelevated dense no-caps").classes(
                "bg-[#1e212b] hover:bg-[#262a36] text-[#e6edf3] border "
                "border-[#2b2f3d] text-xs px-3 py-1.5 rounded-lg"
            )

            ui.button(
                "No Project",
                icon="block",
                on_click=lambda: state.set_project(
                    Path.home() / ".agents" / ".mvgeos" / "sandbox"
                ),
            ).props("unelevated dense no-caps").classes(
                "bg-[#1e212b] hover:bg-[#262a36] text-[#8b949e] border "
                "border-[#2b2f3d] text-xs px-3 py-1.5 rounded-lg"
            )

    return container
