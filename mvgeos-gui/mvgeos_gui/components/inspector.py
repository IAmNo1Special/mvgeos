"""Right context inspector panel component with collapsible accordions."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.models import BackgroundTask, TaskStatus

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
