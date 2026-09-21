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
            "w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] "
            "rounded-xl p-0 overflow-hidden"
        ),
    ):
        with ui.row().classes(
            "w-full h-11 px-4 items-center justify-between "
            "border-b border-[var(--border-subtle)] bg-[var(--bg-raised)]"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("difference", size="16px").classes(
                    "text-[var(--accent-primary)]"
                )
                ui.label(diff_view.file_path).classes(
                    "text-sm font-medium text-[var(--text-primary)] font-mono"
                )
                ui.badge(diff_view.status, color="grey-9").props(
                    "rounded dense"
                ).classes("text-[10px] text-[var(--text-secondary)] font-mono")
                if add_total > 0:
                    ui.badge(
                        f"+{add_total}",
                        color="green-9",
                    ).props("rounded dense").classes("text-[10px] text-white font-mono")
                if del_total > 0:
                    ui.badge(
                        f"-{del_total}",
                        color="red-9",
                    ).props("rounded dense").classes("text-[10px] text-white font-mono")
            ui.button(
                icon="close",
                on_click=lambda: dialog.close(),
            ).props("flat dense round text-color=grey-5 size=sm")

        view_mode: list[str] = ["unified"]

        def _render_unified() -> None:
            content_container.clear()
            with content_container:
                for hunk in diff_view.hunks:
                    with ui.column().classes(
                        "w-full mb-2 rounded-lg border border-[var(--border-subtle)] "
                        "overflow-hidden"
                    ):
                        with ui.row().classes(
                            "w-full px-3 py-1.5 bg-[var(--bg-raised)] items-center "
                            "gap-2"
                        ):
                            ui.label(
                                f"@@ -{hunk.source_start},{hunk.source_length}"
                                f" +{hunk.target_start},{hunk.target_length} @@"
                            ).classes("text-[10px] text-[var(--text-muted)] font-mono")
                        for line in hunk.lines:
                            with ui.row().classes(
                                "w-full items-stretch hover:bg-[var(--bg-card)]"
                            ):
                                line_no = (
                                    str(line.old_line_number)
                                    if line.old_line_number is not None
                                    else ""
                                )
                                ui.label(line_no).classes(
                                    "w-10 text-right pr-3 text-[10px] "
                                    "text-[var(--text-muted)] font-mono select-none "
                                    "border-r border-[var(--border-subtle)]"
                                )
                                line_no_new = (
                                    str(line.new_line_number)
                                    if line.new_line_number is not None
                                    else ""
                                )
                                ui.label(line_no_new).classes(
                                    "w-10 text-right pr-3 text-[10px] "
                                    "text-[var(--text-muted)] font-mono select-none "
                                    "border-r border-[var(--border-subtle)]"
                                )
                                prefix = " "
                                color = "text-[var(--text-primary)]"
                                if line.line_type == "addition":
                                    prefix = "+"
                                    color = "text-[var(--addition-green)]"
                                elif line.line_type == "deletion":
                                    prefix = "-"
                                    color = "text-[var(--deletion-red)]"
                                ui.label(f"{prefix}{line.content}").classes(
                                    "flex-grow text-xs font-mono "
                                    f"{color} whitespace-pre"
                                )

        def _render_side_by_side() -> None:
            content_container.clear()
            with content_container:
                for hunk in diff_view.hunks:
                    with ui.row().classes(
                        "w-full mb-2 rounded-lg border border-[var(--border-subtle)] "
                        "overflow-hidden"
                    ):
                        with ui.column().classes(
                            "w-1/2 border-r border-[var(--border-subtle)]"
                        ):
                            ui.label(
                                f"@@ -{hunk.source_start},{hunk.source_length} @@"
                            ).classes(
                                "w-full px-3 py-1.5 bg-[var(--bg-raised)] text-[10px] "
                                "text-[var(--text-muted)] font-mono border-b "
                                "border-[var(--border-subtle)]"
                            )
                            for line in hunk.lines:
                                if line.line_type in ("context", "deletion"):
                                    with ui.row().classes(
                                        "w-full items-stretch hover:bg-[var(--bg-card)]"
                                    ):
                                        line_no = (
                                            str(line.old_line_number)
                                            if line.old_line_number is not None
                                            else ""
                                        )
                                        ui.label(line_no).classes(
                                            "w-10 text-right pr-3 text-[10px] "
                                            "text-[var(--text-muted)] font-mono "
                                            "select-none "
                                            "border-r border-[var(--border-subtle)]"
                                        )
                                        prefix = (
                                            " " if line.line_type == "context" else "-"
                                        )
                                        color = (
                                            "text-[var(--deletion-red)]"
                                            if line.line_type == "deletion"
                                            else "text-[var(--text-primary)]"
                                        )
                                        ui.label(f"{prefix}{line.content}").classes(
                                            "flex-grow text-xs font-mono "
                                            f"{color} whitespace-pre"
                                        )
                        with ui.column().classes("w-1/2"):
                            ui.label(
                                f"@@ +{hunk.target_start},{hunk.target_length} @@"
                            ).classes(
                                "w-full px-3 py-1.5 bg-[var(--bg-raised)] text-[10px] "
                                "text-[var(--text-muted)] font-mono border-b "
                                "border-[var(--border-subtle)]"
                            )
                            for line in hunk.lines:
                                if line.line_type in ("context", "addition"):
                                    with ui.row().classes(
                                        "w-full items-stretch hover:bg-[var(--bg-card)]"
                                    ):
                                        line_no = (
                                            str(line.new_line_number)
                                            if line.new_line_number is not None
                                            else ""
                                        )
                                        ui.label(line_no).classes(
                                            "w-10 text-right pr-3 text-[10px] "
                                            "text-[var(--text-muted)] font-mono "
                                            "select-none "
                                            "border-r border-[var(--border-subtle)]"
                                        )
                                        prefix = (
                                            " " if line.line_type == "context" else "+"
                                        )
                                        color = (
                                            "text-[var(--addition-green)]"
                                            if line.line_type == "addition"
                                            else "text-[var(--text-primary)]"
                                        )
                                        ui.label(f"{prefix}{line.content}").classes(
                                            "flex-grow text-xs font-mono "
                                            f"{color} whitespace-pre"
                                        )

        with ui.row().classes(
            "w-full px-4 py-2 items-center gap-2 border-b "
            "border-[var(--border-subtle)] bg-[var(--bg-raised)]"
        ):
            ui.label("View:").classes("text-[11px] text-[var(--text-secondary)]")
            ui_unified_active = view_mode[0] == "unified"
            ui.button(
                "Unified",
                on_click=lambda: _set_mode("unified"),
            ).props(
                f"flat dense no-caps size=xs "
                f"{'text-color=primary' if ui_unified_active else 'text-color=grey-5'}"
            ).mark("unified_view_btn")
            ui_side_active = view_mode[0] == "side_by_side"
            ui.button(
                "Side by Side",
                on_click=lambda: _set_mode("side_by_side"),
            ).props(
                f"flat dense no-caps size=xs "
                f"{'text-color=primary' if ui_side_active else 'text-color=grey-5'}"
            ).mark("side_by_side_view_btn")

        content_container = ui.column().classes(
            "w-full max-h-[60vh] overflow-auto bg-[var(--bg-sunken)] p-0"
        )
        _render_unified()

        def _set_mode(mode: str) -> None:
            view_mode[0] = mode
            if mode == "unified":
                _render_unified()
            else:
                _render_side_by_side()

    dialog.open()
