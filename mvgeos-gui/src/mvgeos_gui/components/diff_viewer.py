"""Diff viewer panel for reviewing file changes."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_diff_viewer(state: AppState) -> None:
    """Render the diff viewer for the selected file."""
    view = state.get_selected_diff_view()
    if view is None:
        ui.label("No diff selected").classes("text-xs text-[#64748b] p-4")
        return

    with ui.column().classes("w-full h-full overflow-y-auto"):
        # Header
        with ui.row().classes(
            "w-full items-center justify-between p-3 border-b border-[#2b2f3d]"
        ):
            ui.label(view.file_path).classes(
                "text-xs text-[#e6edf3] font-mono truncate flex-1"
            )
            status_colors = {
                "new": "text-[#22c55e]",
                "modified": "text-[#f59e0b]",
                "deleted": "text-[#ef4444]",
            }
            status_color = status_colors.get(view.status, "text-[#8b949e]")
            ui.label(view.status.upper()).classes(
                f"text-[10px] font-bold {status_color} mr-2"
            )
            ui.button(
                icon="close",
                on_click=state.clear_diff_selection,
            ).props("flat dense round text-color=grey-5 size=xs")

        # Stats
        with ui.row().classes(
            "px-3 py-2 gap-3 text-[10px] text-[#8b949e] border-b border-[#2b2f3d]/60"
        ):
            ui.label(f"+{view.additions} additions").classes("text-[#22c55e]")
            ui.label(f"-{view.deletions} deletions").classes("text-[#ef4444]")

        # Hunks
        for hunk in view.hunks:
            hunk_title = (
                f"@@ -{hunk.source_start},{hunk.source_length} "
                f"+{hunk.target_start},{hunk.target_length} @@"
            )
            with (
                ui.expansion(
                    hunk_title,
                    group="diff-hunks",
                ).classes("w-full border-b border-[#2b2f3d]/60"),
                ui.column().classes("w-full font-mono text-xs"),
            ):
                for line in hunk.lines:
                    line_colors = {
                        "addition": "bg-[#22c55e]/10 text-[#22c55e]",
                        "deletion": "bg-[#ef4444]/10 text-[#ef4444]",
                        "context": "text-[#8b949e]",
                    }
                    color = line_colors.get(line.line_type, "text-[#8b949e]")
                    prefix = {"addition": "+", "deletion": "-", "context": " "}.get(
                        line.line_type, " "
                    )
                    with ui.row().classes(f"w-full px-3 py-0.5 {color}"):
                        old_num = (
                            str(line.old_line_number) if line.old_line_number else ""
                        )
                        new_num = (
                            str(line.new_line_number) if line.new_line_number else ""
                        )
                        ui.label(old_num).classes("w-8 text-right text-[#64748b] mr-2")
                        ui.label(new_num).classes("w-8 text-right text-[#64748b] mr-2")
                        ui.label(f"{prefix}{line.content}").classes(
                            "whitespace-pre-wrap"
                        )
