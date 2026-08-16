"""Right context inspector panel component with collapsible accordions."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.components.diff_review import render_diff_modal
from mvgeos_gui.models import BackgroundTask, TaskStatus
from mvgeos_gui.state import AppState

_TASK_STATUS_ICONS: dict[TaskStatus, str] = {
    TaskStatus.RUNNING: "schedule",
    TaskStatus.COMPLETE: "check_circle",
    TaskStatus.ERROR: "error",
}

_TASK_STATUS_COLORS: dict[TaskStatus, str] = {
    TaskStatus.RUNNING: "text-[#3b82f6]",
    TaskStatus.COMPLETE: "text-[#22c55e]",
    TaskStatus.ERROR: "text-[#ef4444]",
}


def _render_background_task_row(task: BackgroundTask) -> None:
    """Render a single background task entry with name, status, and progress."""
    icon_name = _TASK_STATUS_ICONS.get(task.status, "schedule")
    color_class = _TASK_STATUS_COLORS.get(task.status, "text-[#8b949e]")
    status_label = task.status.value if task.status else "unknown"

    with ui.row().classes("w-full items-center gap-1.5 mb-1"):
        ui.icon(icon_name, size="12px").classes(color_class)
        ui.label(task.name).classes("text-[11px] text-[#e6edf3] truncate")
        ui.label(status_label).classes("text-[10px] text-[#6e7681] uppercase")
    if 0 < task.progress <= 1.0:
        ui.linear_progress(value=task.progress, size="xs").classes(
            "w-full h-1.5 mt-0.5"
        )


def render_inspector(state: AppState) -> ui.column:
    """Render the collapsible right context inspector panel."""
    container = ui.column().classes(
        "h-full bg-[#13151b] border-l border-[#2b2f3d] p-0 pb-6 "
        "flex flex-col justify-between transition-all duration-200 shrink-0 select-none"
    )
    if not state.inspector_expanded:
        container.classes("w-0 p-0 hidden overflow-hidden", remove="w-80")
        return container

    container.classes("w-80", remove="w-0 p-0 hidden overflow-hidden")

    with container:
        # Header
        with ui.row().classes(
            "w-full h-11 px-4 items-center justify-between "
            "border-b border-[#2b2f3d] shrink-0"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("layers", size="16px").classes("text-[#3b82f6]")
                ui.label("Context").classes("text-xs font-semibold text-[#e6edf3]")

            ui.button(
                icon="close",
                on_click=state.toggle_inspector,
            ).props("flat dense round text-color=grey-5 size=sm").mark(
                "toggle_inspector_btn"
            )

        # Scrollable Accordions list
        with ui.scroll_area().classes("w-full flex-grow p-2 gap-1"):
            # 1. Subagents
            with (
                ui.expansion("Subagents", icon="hub").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#2b2f3d]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No active subagents").classes("italic text-[11px]")

            # 2. Files Changed
            with (
                ui.expansion("Files Changed", icon="difference").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#2b2f3d]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                if not state.changed_files:
                    ui.label("Working tree clean").classes("italic text-[11px]")
                else:
                    for changed in state.changed_files:
                        with ui.row().classes(
                            "w-full items-center justify-between p-1.5 rounded "
                            "bg-[#13151b] border border-[#252836] mb-1 "
                            "cursor-pointer hover:border-[#3b82f6]"
                        ).on(
                            "click", lambda p=changed.path: state.open_diff_review(p)
                        ):
                            with ui.row().classes(
                                "items-center gap-1.5 overflow-hidden"
                            ):
                                ui.icon("description", size="12px").classes(
                                    "text-[#3b82f6] shrink-0"
                                )
                                ui.label(changed.path).classes(
                                    "text-[11px] text-[#e6edf3] font-mono "
                                    "truncate max-w-[200px]"
                                )
                            with ui.row().classes("items-center gap-1 shrink-0"):
                                if changed.additions > 0:
                                    ui.badge(
                                        f"+{changed.additions}",
                                        color="green-9",
                                    ).props("rounded dense").classes(
                                        "text-[9px] text-white font-mono px-1"
                                    )
                                if changed.deletions > 0:
                                    ui.badge(
                                        f"-{changed.deletions}",
                                        color="red-9",
                                    ).props("rounded dense").classes(
                                        "text-[9px] text-white font-mono px-1"
                                    )
                    with ui.row().classes("w-full mt-1"):
                        ui.button(
                            "Review All",
                            icon="difference",
                            on_click=lambda: (
                                state.open_diff_review(state.changed_files[0].path)
                                if state.changed_files
                                else None
                            ),
                        ).props("flat dense no-caps size=xs").classes(
                            "text-[10px] text-[#3b82f6]"
                        ).mark("review_all_diff_btn")

            # 3. Artifacts
            with (
                ui.expansion("Artifacts", icon="description").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#2b2f3d]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                ui.label("No artifacts generated").classes("italic text-[11px]")

            # 4. Skills Used
            with (
                ui.expansion("Skills Used", icon="auto_stories").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#2b2f3d]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                if not state.active_skills:
                    ui.label("No skills invoked in session").classes(
                        "italic text-[11px]"
                    )
                else:
                    for skill in state.active_skills:
                        with ui.row().classes("w-full items-center gap-1 mb-1"):
                            ui.icon(
                                "auto_stories" if skill.invoked else "library_books",
                                size="12px",
                            ).classes(
                                "text-[#3b82f6]" if skill.invoked else "text-[#6e7681]"
                            )
                            ui.label(skill.name).classes(
                                "text-[12px] font-medium text-[#e6edf3]"
                            )
                        if skill.description:
                            ui.label(skill.description).classes(
                                "text-[11px] text-[#8b949e] ml-5"
                            )
                        meta_parts = []
                        if skill.scope:
                            meta_parts.append(skill.scope)
                        if skill.path:
                            meta_parts.append(skill.path)
                        if meta_parts:
                            ui.label(" · ".join(meta_parts)).classes(
                                "text-[10px] text-[#6e7681] ml-5"
                            )

            # 5. Uploads
            with (
                ui.expansion("Uploads", icon="cloud_upload").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#2b2f3d]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                if not state.uploaded_files:
                    ui.label("No uploaded files").classes("italic text-[11px]")
                else:
                    for name in state.uploaded_files:
                        with ui.row().classes("w-full items-center gap-1.5 mb-1"):
                            ui.icon("insert_drive_file", size="12px").classes(
                                "text-[#8b949e]"
                            )
                            ui.label(str(name)).classes(
                                "text-[11px] text-[#e6edf3] truncate"
                            )

            # 6. Background Tasks
            with (
                ui.expansion("Background Tasks", icon="schedule").classes(
                    "w-full text-xs text-[#e6edf3] border-b border-[#2b2f3d]/60 rounded"
                ),
                ui.column().classes("w-full p-2 text-xs text-[#8b949e]"),
            ):
                if not state.background_tasks:
                    ui.label("No running background tasks").classes(
                        "italic text-[11px]"
                    )
                else:
                    for task in state.background_tasks:
                        _render_background_task_row(task)

    selected_view = state.get_selected_diff_view()
    if selected_view is not None:
        render_diff_modal(state, selected_view)
    return container
