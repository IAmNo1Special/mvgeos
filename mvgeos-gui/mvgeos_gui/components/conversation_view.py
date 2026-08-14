"""Conversation viewport component rendering message bubbles and execution cards."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.components.step_cards import (
    render_contemplation_card,
    render_step_card,
)
from mvgeos_gui.models import ChatMessage
from mvgeos_gui.state import AppState


def _copy_to_clipboard(text: str) -> None:
    """Copy content to the system clipboard and display feedback toast."""
    escaped = text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    ui.run_javascript(f"navigator.clipboard.writeText(`{escaped}`)")
    ui.notify("Copied to clipboard", type="positive", position="bottom")


def render_user_message(msg: ChatMessage) -> ui.column:
    """Render a styled user prompt container bubble."""
    with (
        ui.column().classes(
            "w-full max-w-3xl mx-auto px-6 py-3 items-end"
        ) as container,
        ui.card().classes(
            "w-auto max-w-[85%] bg-[#1e212b] border border-[#2b2f3d] "
            "rounded-2xl p-4 gap-2 shadow-md"
        ),
    ):
        with ui.row().classes(
            "w-full items-center justify-between gap-4 pb-1 border-b border-[#252836]"
        ):
            with ui.row().classes("items-center gap-1.5"):
                ui.icon("account_circle", size="16px").classes("text-[#3b82f6]")
                ui.label("Summoner").classes("text-xs font-semibold text-[#e6edf3]")
            ui.label(msg.timestamp).classes("text-[10px] text-[#64748b] font-mono")

        ui.label(msg.content).classes(
            "text-xs text-[#e6edf3] whitespace-pre-wrap leading-relaxed"
        )

    return container


def render_assistant_message(
    msg: ChatMessage, msg_idx: int, state: AppState
) -> ui.column:
    """Render an Mvge response bubble with live markdown, Mana, and step cards."""
    with (
        ui.column().classes(
            "w-full max-w-3xl mx-auto px-6 py-3 items-start"
        ) as container,
        ui.card().classes(
            "w-full bg-[#181a20] border border-[#2b2f3d] rounded-2xl "
            "p-4 gap-3 shadow-lg"
        ),
    ):
        # Header Row: Mvge Avatar, Model Badge, Mana Usage, Timestamp
        with ui.row().classes(
            "w-full items-center justify-between pb-2 border-b border-[#252836]"
        ):
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

        # Contemplation / Reasoning Card
        if msg.contemplation:
            render_contemplation_card(msg.contemplation, msg.is_streaming)

        # Intermediate Execution Steps
        if msg.steps:
            with ui.column().classes("w-full gap-1 my-1"):
                for step in msg.steps:
                    render_step_card(step)

        # Live Markdown Response Content
        if msg.content:
            ui.markdown(msg.content).classes(
                "text-xs text-[#e6edf3] leading-relaxed markdown-content "
                "max-w-none w-full"
            )

        # Streaming Cursor Indicator
        if msg.is_streaming:
            with ui.row().classes("items-center gap-2 py-1"):
                ui.spinner("dots", size="sm", color="primary")
                stream_label = (
                    "Contemplating..."
                    if (not msg.content and msg.contemplation)
                    else "Channeling response..."
                )
                ui.label(stream_label).classes(
                    "text-[11px] text-[#8b949e] italic animate-pulse"
                )

        # Footer Action Bar: Feedback (Thumbs Up / Down) & Copy
        if not msg.is_streaming and (msg.content or msg.contemplation):
            with ui.row().classes(
                "w-full items-center justify-end gap-1 pt-2 "
                "border-t border-[#252836]/60"
            ):
                # Copy Button
                copy_text = msg.content or msg.contemplation
                with ui.button(
                    icon="content_copy",
                    on_click=lambda c=copy_text: _copy_to_clipboard(c),
                ).props("flat dense round size=xs text-color=grey-5"):
                    ui.tooltip("Copy response")

                # Thumbs Up Button
                up_color = "primary" if msg.feedback == "up" else "grey-5"
                with ui.button(
                    icon="thumb_up",
                    on_click=lambda i=msg_idx: state.set_message_feedback(i, "up"),
                ).props(f"flat dense round size=xs text-color={up_color}"):
                    ui.tooltip("Good response")

                # Thumbs Down Button
                down_color = "negative" if msg.feedback == "down" else "grey-5"
                with ui.button(
                    icon="thumb_down",
                    on_click=lambda i=msg_idx: state.set_message_feedback(i, "down"),
                ).props(f"flat dense round size=xs text-color={down_color}"):
                    ui.tooltip("Poor response")

    return container


def render_conversation_view(state: AppState) -> ui.column:
    """Render the active conversation stream with messages, steps, and feedback."""
    container = ui.column().classes("w-full h-full gap-2 py-4 select-text")

    with container:
        # If no messages in state, show header banner
        if not state.messages:
            with ui.column().classes(
                "w-full items-center justify-center gap-4 py-8 text-center select-none"
            ):
                with ui.row().classes(
                    "w-12 h-12 rounded-2xl bg-[#1e212b] border "
                    "border-[#2b2f3d] items-center justify-center shadow-lg"
                ):
                    ui.icon("chat_bubble", size="24px").classes("text-[#3b82f6]")
                ui.label(state.tome_title).classes(
                    "text-xl font-semibold text-[#e6edf3] tracking-tight"
                )
                if state.active_tome_id:
                    ui.label(state.active_tome_id[:8]).classes(
                        "text-[10px] text-[#64748b] font-mono"
                    )
                ui.label("Active session loaded from Tome").classes(
                    "text-xs text-[#8b949e]"
                )
        else:
            # Render chronological message thread
            for idx, msg in enumerate(state.messages):
                if msg.role == "user":
                    render_user_message(msg)
                else:
                    render_assistant_message(msg, idx, state)

    return container
