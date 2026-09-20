"""Application setup and page route definitions for mvgeos-gui."""

from nicegui import app, ui

from mvgeos_gui.components.keyboard import register_global_keyboard
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
                var isP = (e.key === 'p' || e.key === 'P');
                if ((e.metaKey || e.ctrlKey) && e.shiftKey && isP) {
                    e.preventDefault();
                }
            });
        </script>
    """)

    render_shell(current_state)
    # Global chords (Ctrl/Cmd+Shift+P palette, Esc priority chain). The head
    # script above only preventDefaults the browser's own handling of the
    # chord; this bridge is what actually responds to it. Registered with
    # ignore=[] so the chords work while typing in the composer or any
    # other input.
    register_global_keyboard(current_state)

    # Web mode: a disconnect/refresh must fail closed — pending approval
    # casts are denied because their decision surface is gone. The
    # presenter is resolved lazily: binding happens when the agent is
    # created, which may be after this page is constructed. NiceGUI may
    # also fire this on reconnect, where denial is still the safe answer.
    def _on_client_disconnect() -> None:
        presenter = current_state._approval_presenter
        if presenter is not None:
            presenter.on_client_disconnect()

    ui.context.client.on_disconnect(_on_client_disconnect)
    # Global chords (Ctrl/Cmd+Shift+P palette, Esc priority chain). The head
    # script above only preventDefaults the browser's own handling of the
    # chord; this bridge is what actually responds to it. Registered with
    # ignore=[] so the chords work while typing in the composer or any
    # other input.
    register_global_keyboard(current_state)


def init_app(state: AppState | None = None) -> AppState:
    """Initialize application routes and return the AppState instance."""
    init_db()
    app_state = state or AppState()

    @ui.page("/")
    def index_page() -> None:
        build_page(app_state)

    async def _prewarm_background() -> None:
        try:
            service = app_state.get_agent_service()
            await service.prewarm(app_state)
        except Exception:
            pass

    if not getattr(app, "is_started", False):
        app.on_startup(_prewarm_background)

    return app_state
