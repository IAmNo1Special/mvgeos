"""Diagnostics panel: system health and configuration."""

from nicegui import ui

from mvgeos_gui import __version__
from mvgeos_gui.state import AppState


def render_diagnostics_panel(state: AppState) -> None:
    """Render the diagnostics view."""
    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        ui.label("Diagnostics").classes(
            "text-2xl font-semibold text-[var(--text-primary)]"
        )

        with ui.card().classes(
            "w-full p-4 bg-[var(--bg-card)] border border-[var(--border-subtle)] "
            "rounded-xl"
        ):
            ui.label("System").classes(
                "text-sm font-semibold text-[var(--text-primary)] mb-3"
            )
            _diag_row("App", f"MvgeOS v{__version__}")
            _diag_row("Project", str(state.project_path))
            _diag_row("Model", state.selected_model)
            _diag_row("Mvge Status", state.mvge_status)
            _diag_row("API Key", "Configured" if state.api_key else "Not set")

        with ui.card().classes(
            "w-full p-4 bg-[var(--bg-card)] border border-[var(--border-subtle)] "
            "rounded-xl"
        ):
            ui.label("Session").classes(
                "text-sm font-semibold text-[var(--text-primary)] mb-3"
            )
            _diag_row("Active Tome", state.active_tome_id or "None")
            _diag_row("Title", state.tome_title)
            _diag_row("Messages", str(len(state.messages)))
            _diag_row("Mana Used", f"{state.total_mana_used:,}")
            _diag_row("Channeling", "Yes" if state.is_channeling else "No")

        with ui.row().classes("mt-4"):
            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("flat no-caps text-color=grey-5")


def _diag_row(label: str, value: str) -> None:
    with ui.row().classes(
        "w-full items-center justify-between gap-3 py-1 "
        "border-b border-[var(--border-subtle-a60)] "
        "no-wrap"
    ):
        ui.label(label).classes("text-xs text-[var(--text-secondary)] shrink-0")
        ui.label(value).classes(
            "text-xs text-[var(--text-primary)] font-mono text-right break-all min-w-0"
        )
