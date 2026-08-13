"""Application setup and page route definitions for mvgeos-gui."""

from nicegui import ui

from mvgeos_gui.components.shell import render_shell
from mvgeos_gui.state import AppState
from mvgeos_gui.styles import inject_theme


def build_page(state: AppState | None = None) -> None:
    """Construct the Antigravity GUI layout on the current page."""
    current_state = state or AppState()
    current_state.load_tomes()
    inject_theme()

    @ui.refreshable
    def shell_view() -> None:
        render_shell(current_state)

    shell_view()
    current_state.subscribe(lambda: shell_view.refresh())


def init_app(state: AppState | None = None) -> AppState:
    """Initialize application routes and return the AppState instance."""
    app_state = state or AppState()

    @ui.page("/")
    def index_page() -> None:
        build_page(app_state)

    return app_state
