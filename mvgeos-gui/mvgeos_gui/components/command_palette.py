"""Command palette quick switcher (Ctrl/Cmd+K)."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_command_palette(state: AppState) -> None:
    """Render the command palette dialog."""
    if not getattr(state, "_command_palette_open", False):
        return

    with (
        ui.dialog().props("maximized") as dialog,
        ui.card().classes(
            "w-full max-w-2xl mx-auto mt-20 bg-[#13151b] border "
            "border-[#2b2f3d] rounded-xl shadow-2xl"
        ),
    ):
        ui.label("Quick Switcher").classes(
            "text-sm font-semibold text-[#e6edf3] mb-3 px-4 pt-4"
        )

        search_input = (
            ui.input(placeholder="Type a command, session, or file...")
            .props("dense dark outlined rounded borderless bg-[#1e212b] text-white")
            .classes("w-full mb-3 mx-4")
        )

        def close_palette() -> None:
            state._command_palette_open = False
            dialog.close()

        results = [
            ("Chat", "chat", "chat_bubble_outline"),
            ("Sessions", "sessions", "history"),
            ("Timeline", "timeline", "activity"),
            ("Packages", "packages", "package"),
            ("Notes", "notes", "sticky_note_2"),
            ("Skills", "skills", "auto_awesome"),
            ("Diagnostics", "diagnostics", "stethoscope"),
            ("Settings", "settings", "settings"),
        ]

        def open_view(view_name: str) -> None:
            state.set_current_view(view_name)
            close_palette()

        with ui.column().classes("px-4 pb-4 gap-1 max-h-96 overflow-y-auto"):
            for label, view, icon in results:
                with (
                    ui.row()
                    .classes(
                        "w-full items-center gap-3 px-3 py-2 rounded-lg cursor-pointer "
                        "hover:bg-[#1e212b] text-xs text-[#e6edf3]"
                    )
                    .on("click", lambda _, v=view: open_view(v))
                ):
                    ui.icon(icon, size="16px").classes("text-[#8b949e]")
                    ui.label(label).classes("flex-1")

        search_input.on("keydown.escape", close_palette)


def open_command_palette(state: AppState) -> None:
    """Open the command palette."""
    state._command_palette_open = True
    state.notify()
