"""Shared utilities for mvgeos-gui."""

import re
import urllib.parse

from nicegui import ui
from nicegui.elements.dialog import Dialog

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.

    Removes invalid characters, avoids Windows reserved names,
    and limits length to 255 characters.
    """
    # Replace invalid characters with underscore
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Strip leading/trailing dots and spaces (Windows issues)
    sanitized = sanitized.strip(". ")
    # Avoid Windows reserved names
    if sanitized.upper() in _WINDOWS_RESERVED:
        sanitized = f"_{sanitized}"
    # Limit length
    if len(sanitized) > 255:
        sanitized = sanitized[:255]
    return sanitized or "artifact"


def js_escape(text: str) -> str:
    """Escape text for safe insertion into a JavaScript template literal.

    Handles backslashes, backticks, dollar signs, newlines, carriage returns,
    tabs, single quotes, and </ sequence to prevent JS injection/syntax errors.
    """
    return (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("'", "\\'")
        .replace("</", "<\\/")
    )


def data_uri_escape(text: str) -> str:
    """Escape text for safe use in a data: URI."""
    return urllib.parse.quote(text, safe="")


def copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard with feedback notification."""
    escaped = js_escape(text)
    ui.run_javascript(f"navigator.clipboard.writeText(`{escaped}`)")
    ui.notify("Copied to clipboard", type="positive", position="bottom")


def download_artifact(title: str, content: str) -> None:
    """Download artifact content as a text file."""
    filename = f"{_sanitize_filename(title)}.md"
    blob = f"data:text/plain;charset=utf-8,{data_uri_escape(content)}"
    ui.run_javascript(
        f"const a = document.createElement('a'); a.href = `{blob}`; "
        f"a.download = `{filename}`; a.click();"
    )
    ui.notify(f"Downloading {filename}", type="positive", position="bottom")


_FOCUS_TRAP_JS = (
    "(e) => {"
    " const root = e.target.closest('.q-dialog');"
    " if (!root) return;"
    " const sel = 'a[href], button:not([disabled]), input:not([disabled]),'"
    " + ' select:not([disabled]), textarea:not([disabled]),'"
    " + ' [tabindex]:not([tabindex=\"-1\"])';"
    " const items = [...root.querySelectorAll(sel)]"
    " .filter((el) => el.getClientRects().length > 0);"
    " if (items.length === 0) return;"
    " const first = items[0];"
    " const last = items[items.length - 1];"
    " const active = document.activeElement;"
    " if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }"
    " else if (!e.shiftKey && active === last)"
    " { e.preventDefault(); first.focus(); }"
    "}"
)


def install_focus_trap(dialog: Dialog) -> None:
    """Trap Tab navigation inside an open dialog.

    Registers a client-side Tab keydown handler on the dialog that wraps
    focus from the last focusable element back to the first (and vice versa
    with Shift+Tab), instead of letting Tab escape behind the modal.
    """
    dialog.on("keydown.tab", None, js_handler=_FOCUS_TRAP_JS)
