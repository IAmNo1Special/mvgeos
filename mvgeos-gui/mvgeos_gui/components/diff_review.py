"""Interactive syntax-highlighted Diff Review modal component."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.models import DiffView


def render_diff_modal(state: object, diff_view: DiffView) -> None:
    """Render an interactive Diff Review modal for the given DiffView."""
    add_total = diff_view.additions
    del_total = diff_view.deletions

    def _on_close() -> None:
        clear_fn = getattr(state, "clear_diff_selection", None)
        if clear_fn is not None:
            clear_fn()

    with (
        ui.dialog().classes("w-full max-w-4xl").on("close", _on_close) as dialog,
        ui.card().classes(
            "w-full bg-[#13151b] border border-[#2b2f3d] rounded-xl p-0 overflow-hidden"
        ),
    ):
        with ui.row().classes(
            "w-full h-11 px-4 items-center justify-between "
            "border-b border-[#2b2f3d] bg-[#1a1d26]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("difference", size="16px").classes("text-[#3b82f6]")
                ui.label(diff_view.file_path).classes(
                    "text-sm font-medium text-[#e6edf3] font-mono"
                )
                ui.badge(diff_view.status, color="grey-9").props(
                    "rounded dense"
                ).classes("text-[10px] text-[#8b949e] font-mono")
                if add_total > 0:
                    ui.badge(
                        f"+{add_total}",
                        color="green-9",
                    ).props("rounded dense").classes(
                        "text-[10px] text-white font-mono"
                    )
                if del_total > 0:
                    ui.badge(
                        f"-{del_total}",
                        color="red-9",
                    ).props("rounded dense").classes(
                        "text-[10px] text-white font-mono"
                    )
            ui.button(
                icon="close",
                on_click=lambda: (dialog.close()),
            ).props("flat dense round text-color=grey-5 size=sm")

        view_mode: list[str] = ["unified"]

        def _render_unified() -> None:
            content_container.clear()
            with content_container:
                for hunk in diff_view.hunks:
                    with ui.column().classes(
                        "w-full mb-2 rounded-lg border border-[#2b2f3d] overflow-hidden"
                    ):
                        with ui.row().classes(
                            "w-full px-3 py-1.5 bg-[#1a1d26] items-center gap-2"
                        ):
                            ui.label(
                                f"@@ -{hunk.source_start},{hunk.source_length}"
                                f" +{hunk.target_start},{hunk.target_length} @@"
                            ).classes("text-[10px] text-[#64748b] font-mono")
                        for line in hunk.lines:
                            with ui.row().classes(
                                "w-full items-stretch hover:bg-[#1e212b]"
                            ):
                                line_no = (
                                    str(line.old_line_number)
                                    if line.old_line_number is not None
                                    else ""
                                )
                                ui.label(line_no).classes(
                                    "w-10 text-right pr-3 text-[10px] "
                                    "text-[#64748b] font-mono select-none "
                                    "border-r border-[#2b2f3d]"
                                )
                                line_no_new = (
                                    str(line.new_line_number)
                                    if line.new_line_number is not None
                                    else ""
                                )
                                ui.label(line_no_new).classes(
                                    "w-10 text-right pr-3 text-[10px] "
                                    "text-[#64748b] font-mono select-none "
                                    "border-r border-[#2b2f3d]"
                                )
                                prefix = " "
                                color = "text-[#e6edf3]"
                                if line.line_type == "addition":
                                    prefix = "+"
                                    color = "text-[#22c55e]"
                                elif line.line_type == "deletion":
                                    prefix = "-"
                                    color = "text-[#ef4444]"
                                ui.label(f"{prefix}{line.content}").classes(
                                    "flex-grow text-xs font-mono "
                                    f"{color} whitespace-pre"
                                )

        def _render_side_by_side() -> None:
            content_container.clear()
            with content_container:
                for hunk in diff_view.hunks:
                    with ui.row().classes(
                        "w-full mb-2 rounded-lg border border-[#2b2f3d] overflow-hidden"
                    ):
                        with ui.column().classes("w-1/2 border-r border-[#2b2f3d]"):
                            ui.label(
                                f"@@ -{hunk.source_start},{hunk.source_length} @@"
                            ).classes(
                                "w-full px-3 py-1.5 bg-[#1a1d26] text-[10px] "
                                "text-[#64748b] font-mono border-b border-[#2b2f3d]"
                            )
                            for line in hunk.lines:
                                if line.line_type in ("context", "deletion"):
                                    with ui.row().classes(
                                        "w-full items-stretch hover:bg-[#1e212b]"
                                    ):
                                        line_no = (
                                            str(line.old_line_number)
                                            if line.old_line_number is not None
                                            else ""
                                        )
                                        ui.label(line_no).classes(
                                            "w-10 text-right pr-3 text-[10px] "
                                            "text-[#64748b] font-mono select-none "
                                            "border-r border-[#2b2f3d]"
                                        )
                                        prefix = (
                                            " "
                                            if line.line_type == "context"
                                            else "-"
                                        )
                                        color = (
                                            "text-[#ef4444]"
                                            if line.line_type == "deletion"
                                            else "text-[#e6edf3]"
                                        )
                                        ui.label(f"{prefix}{line.content}").classes(
                                            "flex-grow text-xs font-mono "
                                            f"{color} whitespace-pre"
                                        )
                        with ui.column().classes("w-1/2"):
                            ui.label(
                                f"@@ +{hunk.target_start},{hunk.target_length} @@"
                            ).classes(
                                "w-full px-3 py-1.5 bg-[#1a1d26] text-[10px] "
                                "text-[#64748b] font-mono border-b border-[#2b2f3d]"
                            )
                            for line in hunk.lines:
                                if line.line_type in ("context", "addition"):
                                    with ui.row().classes(
                                        "w-full items-stretch hover:bg-[#1e212b]"
                                    ):
                                        line_no = (
                                            str(line.new_line_number)
                                            if line.new_line_number is not None
                                            else ""
                                        )
                                        ui.label(line_no).classes(
                                            "w-10 text-right pr-3 text-[10px] "
                                            "text-[#64748b] font-mono select-none "
                                            "border-r border-[#2b2f3d]"
                                        )
                                        prefix = (
                                            " "
                                            if line.line_type == "context"
                                            else "+"
                                        )
                                        color = (
                                            "text-[#22c55e]"
                                            if line.line_type == "addition"
                                            else "text-[#e6edf3]"
                                        )
                                        ui.label(f"{prefix}{line.content}").classes(
                                            "flex-grow text-xs font-mono "
                                            f"{color} whitespace-pre"
                                        )

        with ui.row().classes(
            "w-full px-4 py-2 items-center gap-2 border-b border-[#2b2f3d] bg-[#1a1d26]"
        ):
            ui.label("View:").classes("text-[11px] text-[#8b949e]")
            ui_unified_active = (
                view_mode[0] == "unified"
            )
            ui.button(
                "Unified",
                on_click=lambda: (_set_mode("unified")),
            ).props(
                f"flat dense no-caps size=xs "
                f"{'text-color=primary' if ui_unified_active else 'text-color=grey-5'}"
            ).mark("unified_view_btn")
            ui_side_active = (
                view_mode[0] == "side_by_side"
            )
            ui.button(
                "Side by Side",
                on_click=lambda: (_set_mode("side_by_side")),
            ).props(
                f"flat dense no-caps size=xs "
                f"{'text-color=primary' if ui_side_active else 'text-color=grey-5'}"
            ).mark("side_by_side_view_btn")

        content_container = ui.column().classes(
            "w-full max-h-[60vh] overflow-auto bg-[#0e1117] p-0"
        )
        _render_unified()

        def _set_mode(mode: str) -> None:
            view_mode[0] = mode
            if mode == "unified":
                _render_unified()
            else:
                _render_side_by_side()

    dialog.open()
