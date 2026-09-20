"""Global keyboard shortcuts for the MvgeOS GUI.

Two chords, both handled here as the single owner of global key dispatch:

- Ctrl/Cmd+Shift+P toggles the command palette from anywhere, including
  while typing in the composer (registered with ``ignore=[]`` so inputs do
  not swallow it).
- Escape follows a strict priority chain and performs exactly one action
  per keypress: close the autocomplete popup if open, else close the
  command palette if open, else interrupt channeling if active.

Element-level ``keydown.escape`` handlers were removed in favor of this
central chain: per-element handlers fire during bubble before a
document-level listener, which made "close popup AND interrupt" possible
on a single Esc press.
"""

from __future__ import annotations

from nicegui import ui
from nicegui.events import KeyEventArguments

from mvgeos_gui.state import AppState


def handle_global_key(state: AppState, event: KeyEventArguments) -> None:
    """Dispatch one global key event. Pure logic over AppState; unit-testable."""
    action = event.action
    if not action.keydown or action.repeat:
        return

    modifiers = event.modifiers
    key_name = (event.key.name or "").lower()

    if (
        key_name == "p"
        and (modifiers.ctrl or modifiers.meta)
        and modifiers.shift
        and not modifiers.alt
    ):
        state.toggle_command_palette()
        return

    if key_name == "escape":
        autocomplete = state.get_autocomplete_service()
        if autocomplete.is_open:
            autocomplete.close()
            return
        if state.command_palette_open:
            state.set_command_palette_open(False)
            return
        if state.is_channeling:
            state.stop_channeling()


def register_global_keyboard(state: AppState) -> None:
    """Register the document-level keyboard listener once per page build."""
    ui.keyboard(lambda event: handle_global_key(state, event), ignore=[])
