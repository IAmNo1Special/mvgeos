"""Application setup and page route definitions for mvgeos-gui."""

import asyncio
import contextlib

from nicegui import app, ui

from mvgeos_gui.components.keyboard import register_global_keyboard
from mvgeos_gui.components.shell import render_shell
from mvgeos_gui.core.database import init_db
from mvgeos_gui.state import AppState, ServerState


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


def _prewarm_client(client_state: AppState) -> None:
    """Warm the per-client agent on page load (best effort, non-blocking)."""
    service = client_state.get_agent_service()

    async def _warm() -> None:
        with contextlib.suppress(Exception):
            await service.prewarm(client_state)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_warm())


def init_app(server: ServerState | None = None) -> ServerState:
    """Initialize application routes and return the ServerState instance.

    Every browser session gets its own per-client AppState minted from the
    server, so no UI state (dialogs, current view, sidebar, transcript,
    plan mode, auth) leaks across sessions. Disconnecting clients are
    dropped fail-closed.
    """
    init_db()
    server_state = server or ServerState()

    @ui.page("/")
    def index_page() -> None:
        client_state = server_state.new_client_state()
        # A returning browser keeps its sidebar preference: seed the fresh
        # per-client flag from the per-browser cookie.
        with contextlib.suppress(Exception):
            if app.storage.user.get("sidebar-collapsed", False):
                client_state.sidebar_open = False
        ui.context.client.on_disconnect(
            lambda: server_state.drop_client_state(client_state)
        )
        build_page(client_state)
        _prewarm_client(client_state)

    return server_state
