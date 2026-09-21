"""Read-only file preview dialog for the workspace file tree."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from mvgeos_gui.state import AppState

_MAX_PREVIEW_BYTES = 200 * 1024


def _read_preview(path: Path) -> str | None:
    """Return preview text for *path*, or ``None`` when not previewable."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    if len(raw) > _MAX_PREVIEW_BYTES:
        raw = raw[:_MAX_PREVIEW_BYTES]
    return raw.decode("utf-8", errors="replace")


def render_file_preview_dialog(state: AppState) -> None:
    """Render the file preview dialog when a preview file is set.

    Rendered from the overlay refreshable (like the other modals), not
    from inside the file tree: the tree lives in a side panel whose
    refreshable may clear its slot while the dialog is open.
    """
    target = state.preview_file
    if target is None:
        return

    def _on_close() -> None:
        state.close_file_preview()

    with (
        ui.dialog().on("close", _on_close) as dialog,
        ui.card().classes(
            "p-4 gap-3 w-full max-w-3xl bg-[#08080a] border border-[#292335] rounded-xl"
        ),
    ):
        ui.label(f"File preview: {target.name}").classes(
            "text-sm font-semibold text-[#eceaf4]"
        ).mark("file_preview_title")
        content = _read_preview(target)
        if content is None:
            ui.label(
                "This file cannot be previewed "
                "(binary, too large, or could not be read)."
            ).classes("text-xs text-[#9c94b3]")
        else:
            ui.code(content, language="text").classes(
                "w-full max-h-[60vh] overflow-y-auto text-xs"
            ).mark("file_preview_body")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Close", on_click=_on_close).props("flat dense").mark(
                "file_preview_close_btn"
            )
    dialog.open()
