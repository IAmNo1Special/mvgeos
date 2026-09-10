"""Bottom status bar for MvgeOS desktop."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_status_bar(state: AppState) -> ui.row:
    """Render the bottom status bar."""
    bar = ui.row().classes(
        "w-full h-7 bg-[#050506] border-t border-[#292335] items-center px-3 shrink-0"
    )

    with bar:
        # Mvge status indicator
        status_colors = {
            "idle": "bg-[#6e6584]",
            "channeling": "bg-[#7b6cf6]",
            "working": "bg-[#22c55e]",
        }
        status_color = status_colors.get(state.mvge_status, "bg-[#6e6584]")
        ui.element("div").classes(f"h-2 w-2 rounded-full {status_color} shrink-0")

        # Mvge label
        ui.label("MvgeOS").classes("text-[10px] text-[#6e6584] ml-2 mr-4")

        # Active model
        if state.selected_model:
            model_slug = state.selected_model.split("/")[-1].split(":")[0]
            ui.label(model_slug).classes("text-[10px] text-[#9c94b3] font-mono mr-4")

        # Mana usage
        if state.total_mana_used > 0:
            ui.label(f"{state.total_mana_used:,} Mana").classes(
                "text-[10px] text-[#f59e0b] font-mono mr-4"
            )

        # Streaming indicator
        if state.is_channeling:
            ui.label("Channeling...").classes("text-[10px] text-[#7b6cf6] italic mr-4")

        # Spacer
        ui.element("div").classes("flex-1")

        # Context / compact toggles
        with ui.row().classes("items-center gap-3"):
            ui.button(
                icon="terminal",
                on_click=state.toggle_terminal,
            ).props("flat dense round text-color=grey-5 size=xs").mark(
                "toggle_terminal_btn"
            )
            ui.button(
                icon="dock" if state.review_open else "view_sidebar",
                on_click=state.toggle_review,
            ).props("flat dense round text-color=grey-5 size=xs").mark(
                "toggle_review_btn"
            )
            ui.button(
                icon="view_sidebar" if state.sidebar_open else "menu",
                on_click=state.toggle_sidebar,
            ).props("flat dense round text-color=grey-5 size=xs").mark(
                "toggle_sidebar_btn"
            )

    return bar
