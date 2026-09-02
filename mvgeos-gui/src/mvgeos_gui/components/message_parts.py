"""Decomposed message bubble components for granular rendering."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.components.artifact_drawer import render_artifact_card
from mvgeos_gui.components.step_cards import (
    render_contemplation_card,
    render_step_card,
)
from mvgeos_gui.models import ChatMessage, MessagePartType
from mvgeos_gui.state import AppState
from mvgeos_gui.utils import copy_to_clipboard


def render_message_header(msg: ChatMessage) -> ui.row:
    """Render the header row: avatar, model badge, mana usage, timestamp."""
    with ui.row().classes(
        "w-full items-center justify-between pb-2 border-b border-[#252836]"
    ) as row:
        with ui.row().classes("items-center gap-2"):
            with ui.row().classes(
                "w-6 h-6 rounded-lg bg-[#3b82f6]/20 border "
                "border-[#3b82f6]/40 items-center justify-center"
            ):
                ui.icon("auto_awesome", size="14px").classes("text-[#3b82f6]")
            ui.label("Mvge").classes("text-xs font-semibold text-[#e6edf3]")
            if msg.model:
                model_slug = msg.model.split("/")[-1].split(":")[0]
                ui.badge(model_slug, color="grey-9").props("rounded dense").classes(
                    "text-[10px] text-[#8b949e] font-mono"
                )

        with ui.row().classes("items-center gap-2"):
            if msg.mana_used > 0:
                with ui.row().classes(
                    "items-center gap-1 px-2 py-0.5 rounded "
                    "bg-[#1e212b] border border-[#2b2f3d]"
                ):
                    ui.icon("bolt", size="12px").classes("text-[#f59e0b]")
                    ui.label(f"{msg.mana_used:,} Mana").classes(
                        "text-[10px] text-[#f59e0b] font-mono"
                    )
            ui.label(msg.timestamp).classes("text-[10px] text-[#64748b] font-mono")

    return row


def render_message_parts(msg: ChatMessage, state: AppState, msg_idx: int = 0) -> None:
    """Render sequential message parts in chronological order."""
    for part_idx, part in enumerate(msg.parts):
        if part.part_type == MessagePartType.CONTEMPLATION:
            if part.text:
                render_contemplation_card(
                    part.text,
                    msg.is_streaming,
                    card_id=f"thought_{msg_idx}_{part_idx}",
                    state=state,
                )
        elif part.part_type == MessagePartType.STEP:
            if part.step:
                render_step_card(
                    part.step,
                    card_id=f"step_{msg_idx}_{part_idx}",
                    state=state,
                )
        elif part.part_type == MessagePartType.TEXT:
            if part.text:
                ui.markdown(part.text).classes("markdown-content max-w-none w-full")
        elif part.part_type == MessagePartType.ARTIFACT and part.artifact:
            render_artifact_card(part.artifact, state)


def render_streaming_indicator(msg: ChatMessage) -> ui.row | None:
    """Render the streaming cursor indicator."""
    if not msg.is_streaming:
        return None
    with ui.row().classes("items-center gap-2 py-1") as row:
        ui.spinner("dots", size="sm", color="primary")
        stream_label = (
            "Contemplating..."
            if (not msg.content and msg.contemplation)
            else "Channeling response..."
        )
        ui.label(stream_label).classes(
            "text-[11px] text-[#8b949e] italic animate-pulse"
        )
    return row


def render_error_display(msg: ChatMessage) -> ui.row | None:
    """Render error message if present."""
    if not getattr(msg, "is_error", False):
        return None
    error_message = getattr(msg, "error_message", None)
    if not error_message:
        return None
    with ui.row().classes("items-start gap-2 mb-2") as row:
        ui.icon("error", size="14px").classes("text-[#ef4444]")
        ui.label(error_message).classes("text-xs text-[#ef4444]")
    return row


def render_message_footer(
    msg: ChatMessage, msg_idx: int, state: AppState
) -> ui.row | None:
    """Render footer action bar: copy, thumbs up/down."""
    if msg.is_streaming and not (msg.content or msg.contemplation):
        return None
    with ui.row().classes(
        "w-full items-center justify-end gap-1 pt-2 border-t border-[#252836]/60"
    ) as row:
        copy_text = msg.content or "\n\n".join(msg.contemplation)
        with ui.button(
            icon="content_copy", on_click=lambda c=copy_text: copy_to_clipboard(c)
        ).props("flat dense round size=xs text-color=grey-5"):
            ui.tooltip("Copy response")

        up_color = "primary" if msg.feedback == "up" else "grey-5"
        with ui.button(
            icon="thumb_up",
            on_click=lambda i=msg_idx: state.set_message_feedback(i, "up"),
        ).props(f"flat dense round size=xs text-color={up_color}"):
            ui.tooltip("Good response")

        down_color = "negative" if msg.feedback == "down" else "grey-5"
        with ui.button(
            icon="thumb_down",
            on_click=lambda i=msg_idx: state.set_message_feedback(i, "down"),
        ).props(f"flat dense round size=xs text-color={down_color}"):
            ui.tooltip("Poor response")

    return row


def render_assistant_message(
    msg: ChatMessage, msg_idx: int, state: AppState
) -> ui.column:
    """Compose all parts into a complete assistant message bubble."""
    with (
        ui.column().classes(
            "w-full max-w-3xl mx-auto px-6 py-3 items-start"
        ) as container,
        ui.card().classes(
            "w-full bg-[#181a20] border border-[#2b2f3d] rounded-2xl "
            "p-4 gap-3 shadow-lg"
        ),
    ):
        render_message_header(msg)
        render_message_parts(msg, state, msg_idx=msg_idx)
        render_streaming_indicator(msg)
        render_error_display(msg)
        render_message_footer(msg, msg_idx, state)

    return container
