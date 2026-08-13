"""Floating bottom input card dock component."""

from nicegui import ui

from mvgeos_gui.state import AppState

AVAILABLE_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemini-2.5-pro",
    "anthropic/claude-3-5-sonnet",
    "openai/gpt-4o",
]


def render_input_dock(state: AppState) -> ui.column:
    """Render floating input dock at bottom of conversation viewport."""
    wrapper = ui.column().classes("w-full max-w-3xl mx-auto px-6 pb-8 pt-2 shrink-0")

    with (
        wrapper,
        ui.card().classes(
            "w-full bg-[#1e212b] border border-[#2b2f3d] rounded-2xl p-4 gap-3 "
            "shadow-2xl focus-within:border-[#3b82f6] transition-colors"
        ),
    ):
        # Prompt textarea with symmetrical horizontal padding
        ui.textarea(placeholder="Ask anything. @ to mention. / for actions").props(
            "borderless autogrow dark dense hide-bottom-space"
        ).classes(
            "w-full text-xs text-[#e6edf3] bg-transparent resize-none "
            "leading-relaxed min-h-[36px] px-1"
        )

        # Bottom toolbar row inside dock with symmetrical horizontal padding
        with ui.row().classes("w-full items-center justify-between px-1"):
            # Left tools: Attachment (+), Model Selector, Mode Pill
            with ui.row().classes("items-center gap-2"):
                with ui.button(icon="add").props(
                    "flat dense round text-color=grey-4 size=sm"
                ):
                    ui.tooltip("Add context files or images")

                # Model selector dropdown
                ui.select(
                    options=AVAILABLE_MODELS,
                    value=state.selected_model,
                    on_change=lambda e: setattr(state, "selected_model", e.value),
                ).props(
                    "dense options-dense borderless dark options-dark rounded text-xs"
                ).classes("text-xs text-[#8b949e] font-mono max-w-[220px]")

                # Local pill indicator
                with ui.row().classes(
                    "items-center gap-1 px-2 py-0.5 rounded bg-[#13151b] border "
                    "border-[#2b2f3d] text-[11px] text-[#8b949e] cursor-pointer"
                ):
                    ui.icon("terminal", size="12px").classes("text-[#3b82f6]")
                    ui.label("Local").classes("font-normal")
                    ui.icon("expand_more", size="12px")

            # Right action: Mic + Submit / Stop Channeling button
            with ui.row().classes("items-center gap-2"):
                with ui.button(icon="mic").props(
                    "flat dense round text-color=grey-5 size=sm"
                ):
                    ui.tooltip("Voice Input")

                if state.is_channeling:
                    ui.button(
                        icon="stop",
                        on_click=lambda: setattr(state, "is_channeling", False),
                    ).props(
                        "unelevated dense round color=red text-color=white size=sm"
                    ).classes("shadow")
                else:
                    ui.button(
                        icon="arrow_forward",
                        on_click=lambda: ui.notify("Prompt submitted"),
                    ).props(
                        "unelevated dense round color=primary text-color=white size=sm"
                    ).classes("bg-[#3b82f6] hover:bg-[#2563eb] shadow")

    return wrapper
