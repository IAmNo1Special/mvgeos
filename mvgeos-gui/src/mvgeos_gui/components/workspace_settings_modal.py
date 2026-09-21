"""Project Workspace Settings modal component for mvgeos-gui."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from mvgeos_gui.services.config_service import ConfigService, WorkspaceSettings
from mvgeos_gui.state import AppState
from mvgeos_gui.utils import install_focus_trap

CONTEMPLATION_LEVELS = ["none", "low", "medium", "high", "x-high"]


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
        if not project_dir.is_dir():
            ui.notify(
                f"Workspace directory does not exist: {project_dir}",
                type="negative",
            )
            return
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
            "w-full bg-[#08080a] border border-[#292335] rounded-xl p-0 overflow-hidden"
        ),
    ):
        with ui.row().classes(
            "w-full h-11 px-4 items-center justify-between "
            "border-b border-[#292335] bg-[#101014]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("folder_open", size="16px").classes("text-[#7b6cf6]")
                ui.label("Project Workspace Settings").classes(
                    "text-sm font-medium text-[#eceaf4]"
                )
            ui.button(
                icon="close",
                on_click=lambda: dialog.close(),
            ).props("flat dense round text-color=grey-5 size=sm")

        with ui.column().classes("w-full p-4 gap-4 max-h-[70vh] overflow-auto"):
            with ui.row().classes("w-full gap-4"):
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Project Name").classes("text-xs text-[#9c94b3]")
                    project_name_input = (
                        ui.input(
                            value=str(edited["project_name"]),
                            on_change=lambda e: edited.__setitem__(
                                "project_name", e.value
                            ),
                        )
                        .props("dense outlined dark")
                        .classes("w-full")
                        .mark("project_name_input")
                    )

                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Project Directory").classes("text-xs text-[#9c94b3]")
                    ui.label(str(project_dir)).classes(
                        "text-xs text-[#6e6584] font-mono p-2 "
                        "bg-[#050507] rounded border border-[#292335]"
                    )

            with ui.row().classes("w-full gap-4"):  # noqa: SIM117
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Contemplation Level").classes("text-xs text-[#9c94b3]")
                    supported = (
                        state.get_contemplation_levels_for_selected_model()
                        if hasattr(state, "get_contemplation_levels_for_selected_model")
                        else []
                    )
                    options = (
                        list(supported) if supported else list(CONTEMPLATION_LEVELS)
                    )
                    current_val = str(edited["contemplation_level"])
                    if current_val and current_val not in options:
                        options = [current_val, *options]
                    ui.select(
                        options,
                        value=current_val,
                        on_change=lambda e: edited.__setitem__(
                            "contemplation_level", e.value
                        ),
                    ).props("dense outlined dark").classes("w-full").mark(
                        "contemplation_select"
                    )

        with ui.row().classes(
            "w-full px-4 py-3 items-center justify-end gap-2 "
            "border-t border-[#292335] bg-[#101014]"
        ):
            ui.button("Cancel", on_click=lambda: dialog.close()).props(
                "flat dense no-caps text-color=grey-5"
            )
            ui.button("Save", on_click=_save).props(
                "unelevated dense no-caps mvge-glow-btn text-white"
            )

    install_focus_trap(dialog)
    dialog.open()
    project_name_input.run_method("focus")
