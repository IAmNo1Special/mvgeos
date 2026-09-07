"""Application setup and page route definitions for mvgeos-gui."""

from nicegui import ui

from mvgeos_gui.components.shell import render_shell
from mvgeos_gui.core.database import init_db
from mvgeos_gui.state import AppState


def build_page(state: AppState | None = None) -> None:
    """Construct the MvgeOS GUI layout on the current page."""
    current_state = state or AppState()
    current_state.load_tomes()
    from mvgeos_gui.styles import inject_theme

    inject_theme()

    ui.add_head_html("""
        <script>
            document.addEventListener('keydown', function(e) {
                if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
                    e.preventDefault();
                }
            });
        </script>
    """)

    render_shell(current_state)


def init_app(state: AppState | None = None) -> AppState:
    """Initialize application routes and return the AppState instance."""
    init_db()
    app_state = state or AppState()

    @ui.page("/")
    def index_page() -> None:
        build_page(app_state)

    return app_state
