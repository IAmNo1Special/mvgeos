"""Collapsible execution step cards for Mvge execution operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from mvgeos_gui.models import ExecutionStep, StepType

if TYPE_CHECKING:
    from mvgeos_gui.state import AppState

_PREVIEW_LINES = 20


def _truncate_text(text: str, max_lines: int = _PREVIEW_LINES) -> tuple[str, int]:
    """Truncate text to max_lines and return (displayed_text, hidden_lines)."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, 0
    return "\n".join(lines[:max_lines]), len(lines) - max_lines


def _bind_expansion(
    expansion: ui.expansion,
    card_id: str | None,
    state: AppState | None,
) -> None:
    """Bind expansion value changes to AppState without triggering notification
    loops.
    """
    if state is not None and card_id is not None:
        expansion.on_value_change(
            lambda e, cid=card_id: state.set_card_expansion(
                cid, bool(getattr(e, "value", e))
            )
        )


def render_contemplation_card(
    contemplation: str,
    is_streaming: bool = False,
    card_id: str | None = None,
    state: AppState | None = None,
) -> ui.expansion:
    """Render a collapsible 'Thought' reasoning card."""
    initial_val = (
        state.is_card_expanded(card_id, default=is_streaming)
        if (state is not None and card_id is not None)
        else is_streaming
    )
    with (
        ui.expansion(
            text="Thought",
            icon="psychology",
            value=initial_val,
        )
        .props("dense dense-toggle header-class=bg-[#1a1d26] dark")
        .classes(
            "w-full rounded-xl bg-[#14161f] border border-[#262a38] "
            "text-xs text-[#8b949e] my-1"
        ) as expansion,
        ui.column().classes(
            "w-full p-3 bg-[#0f1118] rounded-b-xl border-t border-[#252836]"
        ),
    ):
        ui.markdown(contemplation).classes(
            "markdown-content markdown-contemplation italic max-w-none w-full"
        )
    _bind_expansion(expansion, card_id, state)
    return expansion


def render_worked_card(
    step: ExecutionStep,
    card_id: str | None = None,
    state: AppState | None = None,
) -> ui.expansion:
    """Render a collapsible 'Worked for Xs' execution card."""
    title = step.spell_name or step.title or "Worked for 0.0s"
    initial_val = (
        state.is_card_expanded(card_id, default=False)
        if (state is not None and card_id is not None)
        else False
    )
    with (
        ui.expansion(
            text=title,
            icon="schedule" if step.is_complete else "hourglass_top",
            value=initial_val,
        )
        .props("dense dense-toggle header-class=bg-[#1e212b] dark")
        .classes(
            "w-full rounded-xl bg-[#1e212b] border border-[#2b2f3d] "
            "text-xs text-[#8b949e] my-1"
        ) as expansion,
        ui.column().classes("w-full p-3 gap-2 bg-[#171920] rounded-b-xl"),
    ):
        if step.details:
            for detail in step.details:
                with ui.row().classes("items-center gap-2 text-[11px] text-[#8b949e]"):
                    ui.icon("check_circle", size="12px").classes("text-[#10b981]")
                    ui.label(detail).classes("font-mono")
        else:
            ui.label("Execution completed.").classes(
                "text-[11px] text-[#64748b] italic"
            )
        if step.params:
            params_id = f"{card_id}_params" if card_id else None
            params_val = (
                state.is_card_expanded(params_id, default=False)
                if (state is not None and params_id is not None)
                else False
            )
            with (
                ui.expansion("Parameters", icon="unfold_more", value=params_val)
                .props("dense dense-toggle dark")
                .classes("text-[10px] text-[#64748b]")
            ) as p_exp:
                ui.code(str(step.params)).classes(
                    "w-full text-[10px] bg-[#0e1117] p-2 rounded max-h-32 overflow-auto"
                )
            _bind_expansion(p_exp, params_id, state)
        if step.result:
            preview, hidden = _truncate_text(step.result)
            with ui.column().classes("w-full gap-1"):
                result_id = f"{card_id}_result" if card_id else None
                result_val = (
                    state.is_card_expanded(result_id, default=False)
                    if (state is not None and result_id is not None)
                    else False
                )
                with (
                    ui.expansion("Result", icon="unfold_more", value=result_val)
                    .props("dense dense-toggle dark")
                    .classes("text-[10px] text-[#64748b]")
                ) as r_exp:
                    ui.code(preview).classes(
                        "w-full text-[10px] bg-[#0e1117] p-2 rounded "
                        "max-h-32 overflow-auto"
                    )
                _bind_expansion(r_exp, result_id, state)
                if hidden > 0:
                    ui.label(
                        f"... ({hidden} more lines, expand Result to view)"
                    ).classes("text-[10px] text-[#64748b] italic")
    _bind_expansion(expansion, card_id, state)
    return expansion


def render_files_card(
    step: ExecutionStep,
    card_id: str | None = None,
    state: AppState | None = None,
) -> ui.expansion:
    """Render a collapsible 'Explored N files' card."""
    count = len(step.files)
    title = step.title or f"Explored {count} file{'s' if count != 1 else ''}"
    initial_val = (
        state.is_card_expanded(card_id, default=False)
        if (state is not None and card_id is not None)
        else False
    )

    with (
        ui.expansion(
            text=title,
            icon="find_in_page",
            value=initial_val,
        )
        .props("dense dense-toggle header-class=bg-[#1e212b] dark")
        .classes(
            "w-full rounded-xl bg-[#1e212b] border border-[#2b2f3d] "
            "text-xs text-[#8b949e] my-1"
        ) as expansion,
        ui.column().classes("w-full p-3 gap-2 bg-[#171920] rounded-b-xl"),
    ):
        for idx, f in enumerate(step.files):
            with ui.row().classes(
                "w-full items-center justify-between p-1.5 rounded "
                "bg-[#13151b] border border-[#252836]"
            ):
                with ui.row().classes("items-center gap-2 overflow-hidden"):
                    ui.icon("description", size="14px").classes(
                        "text-[#3b82f6] shrink-0"
                    )
                    ui.label(f.path).classes(
                        "text-xs text-[#e6edf3] font-mono truncate max-w-[320px]"
                    )
                    if f.lines:
                        ui.badge(f.lines, color="grey-9").props(
                            "rounded dense"
                        ).classes("text-[10px] text-[#8b949e] font-mono px-1.5")
                ui.badge(f.operation.upper(), color="blue-9").props(
                    "rounded dense"
                ).classes("text-[9px] text-white font-mono px-1.5")

            if f.details:
                preview, hidden = _truncate_text(f.details)
                with ui.column().classes("w-full gap-1 ml-4"):
                    details_id = f"{card_id}_details_{idx}" if card_id else None
                    details_val = (
                        state.is_card_expanded(details_id, default=False)
                        if (state is not None and details_id is not None)
                        else False
                    )
                    with (
                        ui.expansion(
                            "File details", icon="unfold_more", value=details_val
                        )
                        .props("dense dense-toggle dark")
                        .classes("text-[10px] text-[#64748b]")
                    ) as d_exp:
                        ui.code(preview).classes(
                            "w-full text-[10px] bg-[#0e1117] p-2 rounded "
                            "max-h-32 overflow-auto"
                        )
                    _bind_expansion(d_exp, details_id, state)
                    if hidden > 0:
                        ui.label(f"... ({hidden} more lines, expand to view)").classes(
                            "text-[10px] text-[#64748b] italic"
                        )
    _bind_expansion(expansion, card_id, state)
    return expansion


def render_commands_card(
    step: ExecutionStep,
    card_id: str | None = None,
    state: AppState | None = None,
) -> ui.expansion:
    """Render a collapsible 'Ran N commands' card with terminal container."""
    count = len(step.commands)
    title = step.title or f"Ran {count} command{'s' if count != 1 else ''}"
    initial_val = (
        state.is_card_expanded(card_id, default=False)
        if (state is not None and card_id is not None)
        else False
    )

    with (
        ui.expansion(
            text=title,
            icon="terminal",
            value=initial_val,
        )
        .props("dense dense-toggle header-class=bg-[#1e212b] dark")
        .classes(
            "w-full rounded-xl bg-[#1e212b] border border-[#2b2f3d] "
            "text-xs text-[#8b949e] my-1"
        ) as expansion,
        ui.column().classes("w-full p-3 gap-3 bg-[#171920] rounded-b-xl"),
    ):
        for cmd in step.commands:
            with ui.column().classes(
                "w-full rounded-lg bg-[#0e1117] border border-[#252836] "
                "p-3 gap-2 shadow-inner"
            ):
                # Terminal title row
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.row().classes("items-center gap-1.5"):
                        ui.element("div").classes(
                            "w-2.5 h-2.5 rounded-full bg-[#ef4444]"
                        )
                        ui.element("div").classes(
                            "w-2.5 h-2.5 rounded-full bg-[#f59e0b]"
                        )
                        ui.element("div").classes(
                            "w-2.5 h-2.5 rounded-full bg-[#10b981]"
                        )
                        ui.label("Terminal").classes(
                            "text-[10px] text-[#64748b] font-mono ml-2"
                        )
                    if cmd.duration_seconds > 0:
                        ui.label(f"{cmd.duration_seconds:.2f}s").classes(
                            "text-[10px] text-[#64748b] font-mono"
                        )

                # Command Prompt
                with ui.row().classes("items-center gap-2"):
                    ui.label("$").classes("text-xs text-[#10b981] font-mono font-bold")
                    ui.label(cmd.command).classes(
                        "text-xs text-[#e6edf3] font-mono font-semibold"
                    )

                # Command Output
                if cmd.output:
                    preview, hidden = _truncate_text(cmd.output)
                    with ui.column().classes("w-full gap-1"):
                        with ui.scroll_area().classes(
                            "w-full max-h-48 bg-[#08090c] rounded p-2 "
                            "border border-[#1b1e27]"
                        ):
                            ui.markdown(f"```text\n{preview}\n```").classes(
                                "markdown-content markdown-terminal m-0 "
                                "max-w-none w-full"
                            )
                        if hidden > 0:
                            ui.label(
                                f"... ({hidden} more lines, scroll to view)"
                            ).classes("text-[10px] text-[#64748b] italic")
    _bind_expansion(expansion, card_id, state)
    return expansion


def render_step_card(
    step: ExecutionStep,
    card_id: str | None = None,
    state: AppState | None = None,
) -> ui.expansion:
    """Dispatch step rendering to the appropriate card renderer."""
    if step.step_type == StepType.FILES:
        return render_files_card(step, card_id=card_id, state=state)
    if step.step_type == StepType.COMMANDS:
        return render_commands_card(step, card_id=card_id, state=state)
    return render_worked_card(step, card_id=card_id, state=state)
