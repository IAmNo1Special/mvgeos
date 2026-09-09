"""Project Workspace Settings modal component for mvgeos-gui."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from mvgeos_gui.services.config_service import ConfigService, WorkspaceSettings
from mvgeos_gui.state import AppState

CONTEMPLATION_LEVELS = ["none", "low", "medium", "high"]


def render_workspace_settings_modal(state: AppState) -> None:
    """Render the Project Workspace Settings modal dialog."""
    if not getattr(state, "_show_workspace_settings", False):
        return

    config_service = getattr(state, "_config_service", None) or ConfigService()
    project_dir = state.project_path
    current = config_service.load_workspace_settings(project_dir)

    edited: dict[str, Any] = {
        "project_name": current.project_name or project_dir.name,
        "spells_enabled": list(current.spells_enabled),
        "contemplation_level": current.contemplation_level,
        "temperature": current.temperature,
        "max_tokens": current.max_tokens,
    }

    def _on_close() -> None:
        state._show_workspace_settings = False
        state.notify()

    def _save() -> None:
        try:
            temp = float(edited["temperature"])
            tokens = int(edited["max_tokens"])
        except (ValueError, TypeError):
            temp = 0.7
            tokens = 4096

        config_service.save_workspace_settings(
            project_dir,
            WorkspaceSettings(
                project_name=str(edited["project_name"]),
                spells_enabled=list(edited["spells_enabled"]),
                contemplation_level=str(edited["contemplation_level"]),
                temperature=temp,
                max_tokens=tokens,
            ),
        )
        state.reset_agent()
        state._show_workspace_settings = False
        state.notify()
        ui.notify("Workspace settings saved", type="positive")

    with (
        ui.dialog().classes("w-full max-w-2xl").on("close", _on_close) as dialog,
        ui.card().classes(
            "w-full bg-[#13151b] border border-[#2b2f3d] rounded-xl p-0 overflow-hidden"
        ),
    ):
        with ui.row().classes(
            "w-full h-11 px-4 items-center justify-between "
            "border-b border-[#2b2f3d] bg-[#1a1d26]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder_open", size="16px").classes("text-[#3b82f6]")
                ui.label("Project Workspace Settings").classes(
                    "text-sm font-medium text-[#e6edf3]"
                )
            ui.button(
                icon="close",
                on_click=lambda: dialog.close(),
            ).props("flat dense round text-color=grey-5 size=sm")

        with ui.column().classes("w-full p-4 gap-4 max-h-[70vh] overflow-auto"):
            with ui.row().classes("w-full gap-4"):
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Project Name").classes("text-xs text-[#8b949e]")
                    ui.input(
                        value=str(edited["project_name"]),
                        on_change=lambda e: edited.__setitem__("project_name", e.value),
                    ).props("dense outlined dark").classes("w-full").mark(
                        "project_name_input"
                    )

                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Project Directory").classes("text-xs text-[#8b949e]")
                    ui.label(str(project_dir)).classes(
                        "text-xs text-[#64748b] font-mono p-2 "
                        "bg-[#0e1117] rounded border border-[#2b2f3d]"
                    )

            with ui.row().classes("w-full gap-4"):  # noqa: SIM117
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Contemplation Level").classes("text-xs text-[#8b949e]")
                    ui.select(
                        CONTEMPLATION_LEVELS,
                        value=str(edited["contemplation_level"]),
                        on_change=lambda e: edited.__setitem__(
                            "contemplation_level", e.value
                        ),
                    ).props("dense outlined dark").classes("w-full").mark(
                        "contemplation_select"
                    )

        with ui.row().classes(
            "w-full px-4 py-3 items-center justify-end gap-2 "
            "border-t border-[#2b2f3d] bg-[#1a1d26]"
        ):
            ui.button("Cancel", on_click=lambda: dialog.close()).props(
                "flat dense no-caps text-color=grey-5"
            )
            ui.button("Save", on_click=_save).props(
                "unelevated dense no-caps bg-[#3b82f6] text-white"
            )

    dialog.open()
