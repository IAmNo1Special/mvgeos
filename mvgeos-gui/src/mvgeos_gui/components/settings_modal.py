"""Application Settings modal component for mvgeos-gui."""

from __future__ import annotations

from typing import Any

from mvgeos_provider import get_model_options
from nicegui import ui

from mvgeos_gui.services.config_service import AppSettings, ConfigService
from mvgeos_gui.state import AppState
from mvgeos_gui.utils import install_focus_trap

AVAILABLE_THEMES = ["dark", "light"]


def render_app_settings_modal(state: AppState) -> None:
    """Render the Application Settings modal dialog."""
    if not getattr(state, "_show_app_settings", False):
        return

    config_service = getattr(state, "_config_service", None) or ConfigService()
    current = config_service.load_app_settings()

    edited: dict[str, Any] = {
        "api_key": current.api_key,
        "default_model": current.default_model,
        "mana_limit": current.mana_limit,
        "temperature": current.temperature,
        "theme": current.theme,
    }

    def _on_close() -> None:
        state._show_app_settings = False
        state.notify()

    def _save() -> None:
        errors: list[str] = []
        mana_limit = 0
        try:
            mana_limit = int(edited["mana_limit"])
            if mana_limit <= 0:
                raise ValueError("Mana limit must be a positive integer")
        except (ValueError, TypeError):
            errors.append("Invalid mana limit: must be a positive integer")
        temperature = 0.0
        try:
            temperature = float(edited["temperature"])
            if temperature < 0.0 or temperature > 2.0:
                raise ValueError("Temperature must be between 0.0 and 2.0")
        except (ValueError, TypeError):
            errors.append("Invalid temperature: must be between 0.0 and 2.0")
        if errors:
            ui.notify("\n".join(errors), type="negative", multi_line=True)
            return
        config_service.save_app_settings(
            AppSettings(
                api_key=str(edited["api_key"]),
                default_model=str(edited["default_model"]),
                mana_limit=mana_limit,
                temperature=temperature,
                theme=str(edited["theme"]),
            )
        )
        if str(edited["default_model"]) != state.selected_model:
            state.switch_model(str(edited["default_model"]))
        state._show_app_settings = False
        state.notify()
        ui.notify("Settings saved", type="positive")

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
                ui.icon("settings", size="16px").classes("text-[#7b6cf6]")
                ui.label("Application Settings").classes(
                    "text-sm font-medium text-[#eceaf4]"
                )
            ui.button(
                icon="close",
                on_click=lambda: dialog.close(),
            ).props("flat dense round text-color=grey-5 size=sm")

        with ui.column().classes("w-full p-4 gap-4 max-h-[70vh] overflow-auto"):
            with ui.row().classes("w-full gap-4"):  # noqa: SIM117
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("API Key").classes("text-xs text-[#9c94b3]")
                    api_key_input = (
                        ui.input(
                            value=str(edited["api_key"]),
                            on_change=lambda e: edited.__setitem__("api_key", e.value),
                            password=True,
                            password_toggle_button=True,
                        )
                        .props("dense outlined dark")
                        .classes("w-full")
                        .mark("api_key_input")
                    )

                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Default Model").classes("text-xs text-[#9c94b3]")
                    ui.select(
                        options=get_model_options(),
                        value=str(edited["default_model"]),
                        on_change=lambda e: edited.__setitem__(
                            "default_model", e.value
                        ),
                        with_input=True,
                    ).props("dense outlined dark").classes("w-full").mark(
                        "model_select"
                    )

            with ui.row().classes("w-full gap-4"):  # noqa: SIM117
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Mana Limit (max_tokens)").classes(
                        "text-xs text-[#9c94b3]"
                    )
                    ui.input(
                        value=str(edited["mana_limit"]),
                        on_change=lambda e: edited.__setitem__("mana_limit", e.value),
                    ).props("dense outlined dark type=number").classes("w-full").mark(
                        "mana_limit_input"
                    )

                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Temperature").classes("text-xs text-[#9c94b3]")
                    ui.input(
                        value=str(edited["temperature"]),
                        on_change=lambda e: edited.__setitem__("temperature", e.value),
                    ).props("dense outlined dark type=number step=0.1").classes(
                        "w-full"
                    ).mark("temperature_input")

            with ui.row().classes("w-full gap-4"):  # noqa: SIM117
                with ui.column().classes("flex-1 gap-1"):
                    ui.label("Theme").classes("text-xs text-[#9c94b3]")
                    ui.select(
                        AVAILABLE_THEMES,
                        value=str(edited["theme"]),
                        on_change=lambda e: edited.__setitem__("theme", e.value),
                    ).props("dense outlined dark").classes("w-full").mark(
                        "theme_select"
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
    api_key_input.run_method("focus")
