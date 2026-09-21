"""Right-side review rail showing changed files and session status."""

from nicegui import ui

from mvgeos_gui.state import AppState


def render_review_rail(state: AppState) -> ui.column:
    """Render the right-side review rail."""
    container = (
        ui.column()
        .classes(
            "h-full bg-[var(--bg-surface)] border-l border-[var(--border-subtle)] "
            "shrink-0 "
            "flex flex-col overflow-hidden"
        )
        .style(f"width: {state._review_width}px")
    )

    with container:
        # Header
        with ui.row().classes(
            "w-full h-11 items-center justify-between px-3 "
            "border-b border-[var(--border-subtle)] shrink-0"
        ):
            ui.label("Review").classes(
                "text-xs font-semibold text-[var(--text-primary)] uppercase "
                "tracking-wider"
            )
            ui.button(
                icon="close",
                on_click=state.toggle_review,
            ).props("flat dense round text-color=grey-5").mark("toggle_review_btn")

        # Changed files
        with ui.row().classes(
            "px-3 py-2 border-b "
            "border-[var(--border-subtle-a60)] "
            "items-center justify-between"
        ):
            ui.label("Changed files").classes(
                "text-[10px] font-medium text-[var(--text-muted)] uppercase "
                "tracking-wider"
            )
            ui.button(
                icon="refresh",
                on_click=state.refresh_changed_files,
            ).props("flat dense round text-color=grey-5 size=xs").mark(
                "refresh_changes_btn"
            )

        with ui.column().classes("flex-1 overflow-y-auto px-3 py-2"):
            if not state.changed_files:
                with ui.column().classes("gap-1"):
                    ui.label("No agent changes yet").classes(
                        "text-[11px] text-[var(--text-muted)]"
                    )
                    ui.label(
                        "This panel tracks changes made by the agent in this session."
                    ).classes("text-[10px] text-[var(--text-muted-a70)]")
            else:
                for cf in state.changed_files:
                    with (
                        ui.row()
                        .classes(
                            "w-full items-center gap-2 px-2 py-1.5 rounded-md "
                            "hover:bg-[var(--bg-card)] cursor-pointer text-xs"
                        )
                        .on("click", lambda p=cf.path: state.open_diff_review(p))
                    ):
                        badge_color = {
                            "new": "text-[var(--addition-green)]",
                            "modified": "text-[var(--text-warn)]",
                            "deleted": "text-[var(--deletion-red)]",
                            "renamed": "text-[var(--accent-primary)]",
                        }.get(cf.status, "text-[var(--text-secondary)]")
                        ui.label(cf.status.upper()[:3]).classes(
                            f"text-[10px] font-mono font-bold {badge_color}"
                        )
                        ui.label(cf.path).classes(
                            "text-[var(--text-primary)] truncate flex-1"
                        )
                        with ui.row().classes("items-center gap-1"):
                            if cf.additions:
                                ui.label(f"+{cf.additions}").classes(
                                    "text-[10px] text-[var(--addition-green)]"
                                )
                            if cf.deletions:
                                ui.label(f"-{cf.deletions}").classes(
                                    "text-[10px] text-[var(--deletion-red)]"
                                )

    return container
