"""Render the context window gauge into the status bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from mvgeos_gui.context_usage import build_context_gauge

if TYPE_CHECKING:
    from mvgeos_gui.state import AppState


def render_context_gauge(state: AppState) -> None:
    """Render the gauge; renders nothing when data is missing or unverified."""
    gauge = build_context_gauge(state)
    if gauge is None:
        return
    ui.label(gauge.format()).classes("text-[10px] text-[#9c94b3] font-mono mr-4").mark(
        "context_gauge"
    )
