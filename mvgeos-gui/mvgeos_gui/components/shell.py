"""3-column obsidian shell layout component."""

from nicegui import ui

from mvgeos_gui.components.empty_state import render_empty_state
from mvgeos_gui.components.header import render_header
from mvgeos_gui.components.input_dock import render_input_dock
from mvgeos_gui.components.inspector import render_inspector
from mvgeos_gui.components.sidebar import render_sidebar
from mvgeos_gui.state import AppState


def render_shell(state: AppState) -> ui.row:
    """Render the full 3-column obsidian shell layout."""
    shell_container = ui.row().classes(
        "w-screen h-screen max-h-screen overflow-hidden m-0 p-0 flex "
        "flex-row no-wrap bg-[#181a20]"
    )

    with shell_container:
        # 1. Left Navigation Sidebar
        render_sidebar(state)

        # 2. Center Main Viewport
        with ui.column().classes(
            "flex-grow h-full max-h-screen flex flex-col justify-between "
            "overflow-hidden p-0 m-0 relative bg-[#181a20]"
        ):
            # Top Navigation Header
            render_header(state)

            # Center Scrollable View (Empty State or Chat Stream)
            with ui.scroll_area().classes("w-full flex-grow relative"):
                render_empty_state(state)

            # Floating Bottom Input Dock with proper clearance
            render_input_dock(state)

        # 3. Right Context Inspector
        render_inspector(state)

    return shell_container
