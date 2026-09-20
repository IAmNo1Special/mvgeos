"""Unit tests for the global keyboard shortcut dispatcher.

Ctrl/Cmd+Shift+P toggles the command palette from anywhere (including
inside inputs). Escape follows a strict priority chain: autocomplete
popup first, then the command palette, then channeling interrupt — and
never more than one action per keypress.
"""

from __future__ import annotations

from pathlib import Path

from nicegui.events import (
    KeyboardAction,
    KeyboardKey,
    KeyboardModifiers,
    KeyEventArguments,
)

from mvgeos_gui.components.keyboard import handle_global_key
from mvgeos_gui.state import AppState


def _key_event(
    *,
    name: str,
    ctrl: bool = False,
    meta: bool = False,
    alt: bool = False,
    shift: bool = False,
    keydown: bool = True,
    repeat: bool = False,
) -> KeyEventArguments:
    return KeyEventArguments(
        sender=None,
        client=None,
        action=KeyboardAction(keydown=keydown, keyup=not keydown, repeat=repeat),
        key=KeyboardKey(name=name, code="", location=0),
        modifiers=KeyboardModifiers(alt=alt, ctrl=ctrl, meta=meta, shift=shift),
    )


def _idle_state(tmp_path: Path) -> AppState:
    """Fresh AppState pointed at an empty dir (hermetic autocomplete index)."""
    state = AppState()
    state.project_path = tmp_path
    return state


def test_ctrl_shift_p_opens_palette(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    assert state.command_palette_open is False
    handle_global_key(state, _key_event(name="P", ctrl=True, shift=True))
    assert state.command_palette_open is True


def test_ctrl_shift_p_closes_palette(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    state.set_command_palette_open(True)
    handle_global_key(state, _key_event(name="P", ctrl=True, shift=True))
    assert state.command_palette_open is False


def test_meta_shift_p_toggles_palette(tmp_path: Path) -> None:
    """Cmd+Shift+P on macOS behaves like Ctrl+Shift+P."""
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="P", meta=True, shift=True))
    assert state.command_palette_open is True


def test_plain_p_does_nothing(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="p"))
    assert state.command_palette_open is False


def test_ctrl_p_without_shift_does_nothing(tmp_path: Path) -> None:
    """Ctrl+P without Shift must not open the palette (browser print)."""
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="p", ctrl=True))
    assert state.command_palette_open is False


def test_ctrl_k_no_longer_opens_palette(tmp_path: Path) -> None:
    """The old Ctrl+K chord is dead."""
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="k", ctrl=True))
    assert state.command_palette_open is False


def test_keyup_ignored(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="P", ctrl=True, shift=True, keydown=False))
    assert state.command_palette_open is False


def test_repeat_ignored(tmp_path: Path) -> None:
    """Holding Ctrl+Shift+P must not toggle the palette repeatedly."""
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="P", ctrl=True, shift=True, repeat=True))
    assert state.command_palette_open is False


def test_escape_closes_autocomplete_first(tmp_path: Path) -> None:
    """Esc with autocomplete open closes it — and does nothing else."""
    state = _idle_state(tmp_path)
    ac = state.get_autocomplete_service()
    ac.is_open = True
    state.set_command_palette_open(True)
    state.is_channeling = True
    handle_global_key(state, _key_event(name="Escape"))
    assert ac.is_open is False
    assert state.command_palette_open is True
    assert state.is_channeling is True


def test_escape_closes_palette_second(tmp_path: Path) -> None:
    """Esc with palette open (autocomplete closed) closes it — no interrupt."""
    state = _idle_state(tmp_path)
    state.set_command_palette_open(True)
    state.is_channeling = True
    handle_global_key(state, _key_event(name="Escape"))
    assert state.command_palette_open is False
    assert state.is_channeling is True


def test_escape_interrupts_channeling_when_nothing_open(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    state.is_channeling = True
    handle_global_key(state, _key_event(name="Escape"))
    assert state.is_channeling is False


def test_escape_does_nothing_when_idle(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="Escape"))
    assert state.command_palette_open is False
    assert state.is_channeling is False


def test_unrelated_key_does_nothing(tmp_path: Path) -> None:
    state = _idle_state(tmp_path)
    handle_global_key(state, _key_event(name="Enter"))
    assert state.command_palette_open is False
