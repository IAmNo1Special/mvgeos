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
    wrapper = ui.column().classes("w-full max-w-4xl mx-auto px-4 pb-4 shrink-0")

    with (
        wrapper,
        ui.card().classes(
            "w-full bg-[#1b1e27] border border-[#252936] rounded-xl p-3 gap-2 "
            "shadow-2xl focus-within:border-[#3b82f6] transition-colors"
        ),
    ):
        # Prompt textarea
        ui.textarea(placeholder="Ask anything. @ to mention. / for actions").props(
            "borderless autogrow dark dense hide-bottom-space"
        ).classes(
            "w-full text-xs text-[#e6edf3] bg-transparent resize-none leading-relaxed"
        )

        # Bottom toolbar row inside dock
        with ui.row().classes("w-full items-center justify-between pt-1"):
            # Left tools: Attachment (+) and Model Selector
            with ui.row().classes("items-center gap-2"):
                with ui.button(icon="add").props(
                    "flat dense round text-color=grey-5 size=sm"
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

            # Right action: Submit or Stop Channeling button
            with ui.row().classes("items-center gap-1"):
                if state.is_channeling:
                    ui.button(
                        icon="stop",
                        on_click=lambda: setattr(state, "is_channeling", False),
                    ).props(
                        "unelevated dense round color=red text-color=white size=sm"
                    ).classes("shadow")
                else:
                    ui.button(
                        icon="arrow_upward",
                        on_click=lambda: ui.notify("Prompt submitted"),
                    ).props(
                        "unelevated dense round color=primary text-color=white size=sm"
                    ).classes("bg-[#3b82f6] hover:bg-[#2563eb] shadow")

    return wrapper
