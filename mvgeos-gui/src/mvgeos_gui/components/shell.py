"""Application shell layout: sidebar + main + review rail + status bar."""

from nicegui import ui

from mvgeos_gui.components.artifact_drawer import render_artifact_drawer
from mvgeos_gui.components.chat_panel import render_chat_panel
from mvgeos_gui.components.command_palette import render_command_palette
from mvgeos_gui.components.diagnostics_panel import render_diagnostics_panel
from mvgeos_gui.components.home_screen import render_home_screen
from mvgeos_gui.components.notes_panel import render_notes_panel
from mvgeos_gui.components.packages_panel import render_packages_panel
from mvgeos_gui.components.review_rail import render_review_rail
from mvgeos_gui.components.sessions_panel import render_sessions_panel
from mvgeos_gui.components.settings_modal import render_app_settings_modal
from mvgeos_gui.components.sidebar import render_sidebar
from mvgeos_gui.components.skills_panel import render_skills_panel
from mvgeos_gui.components.status_bar import render_status_bar
from mvgeos_gui.components.timeline_panel import render_timeline_panel
from mvgeos_gui.components.workspace_settings_modal import (
    render_workspace_settings_modal,
)
from mvgeos_gui.state import AppState


def render_shell(state: AppState) -> None:
    """Render the full 3-pane MvgeOS desktop shell."""
    ui.query(".nicegui-content").classes("p-0 m-0")
    ui.add_css("body { overflow: hidden; }")

    with ui.column().classes(
        "w-screen h-screen max-h-screen overflow-hidden m-0 p-0 flex flex-col"
    ):
        with ui.row().classes(
            "flex-1 w-full h-full overflow-hidden m-0 p-0 flex flex-row no-wrap"
        ):
            last_sidebar_state = [
                (
                    state.sidebar_open,
                    state.current_view,
                    state.active_tome_id,
                    len(state.loaded_tomes),
                    str(state.project_path),
                )
            ]

            @ui.refreshable
            def sidebar_container() -> None:
                if state.sidebar_open:
                    render_sidebar(state)
                last_sidebar_state[0] = (
                    state.sidebar_open,
                    state.current_view,
                    state.active_tome_id,
                    len(state.loaded_tomes),
                    str(state.project_path),
                )

            sidebar_container()

            def _on_sidebar_check() -> None:
                cur = (
                    state.sidebar_open,
                    state.current_view,
                    state.active_tome_id,
                    len(state.loaded_tomes),
                    str(state.project_path),
                )
                if cur != last_sidebar_state[0]:
                    sidebar_container.refresh()

            state.subscribe(_on_sidebar_check)

            with ui.column().classes(
                "flex-1 w-full h-full flex flex-col overflow-hidden"
            ):
                current_rendered_view = [state.current_view]

                @ui.refreshable
                def main_content() -> None:
                    view = state.current_view
                    current_rendered_view[0] = view
                    if view == "home":
                        render_home_screen(state)
                    elif view == "sessions":
                        render_sessions_panel(state)
                    elif view == "skills":
                        render_skills_panel(state)
                    elif view == "notes":
                        render_notes_panel(state)
                    elif view == "diagnostics":
                        render_diagnostics_panel(state)
                    elif view == "timeline":
                        render_timeline_panel(state)
                    elif view == "packages":
                        render_packages_panel(state)
                    else:
                        render_chat_panel(state)

                main_content()

                def _on_view_change() -> None:
                    if current_rendered_view[0] != state.current_view:
                        main_content.refresh()

                state.subscribe(_on_view_change)

            last_review_state = [
                (
                    state.review_open,
                    state.current_view,
                    len(state.changed_files),
                    state._selected_diff_path,
                )
            ]

            @ui.refreshable
            def review_container() -> None:
                if state.review_open and state.current_view == "chat":
                    render_review_rail(state)
                last_review_state[0] = (
                    state.review_open,
                    state.current_view,
                    len(state.changed_files),
                    state._selected_diff_path,
                )

            review_container()

            def _on_review_check() -> None:
                cur = (
                    state.review_open,
                    state.current_view,
                    len(state.changed_files),
                    state._selected_diff_path,
                )
                if cur != last_review_state[0]:
                    review_container.refresh()

            state.subscribe(_on_review_check)

        with ui.row().classes("w-full h-7 shrink-0 overflow-hidden"):
            last_status_state = [
                (
                    state.mvge_status,
                    state.selected_model,
                    state.total_mana_used,
                    state.is_channeling,
                    state.sidebar_open,
                    state.review_open,
                    state.terminal_open,
                )
            ]

            @ui.refreshable
            def status_bar_container() -> None:
                render_status_bar(state)
                last_status_state[0] = (
                    state.mvge_status,
                    state.selected_model,
                    state.total_mana_used,
                    state.is_channeling,
                    state.sidebar_open,
                    state.review_open,
                    state.terminal_open,
                )

            status_bar_container()

            def _on_status_check() -> None:
                cur = (
                    state.mvge_status,
                    state.selected_model,
                    state.total_mana_used,
                    state.is_channeling,
                    state.sidebar_open,
                    state.review_open,
                    state.terminal_open,
                )
                if cur != last_status_state[0]:
                    status_bar_container.refresh()

            state.subscribe(_on_status_check)

    last_overlay_state = [
        (
            getattr(state, "_command_palette_open", False),
            getattr(state, "_selected_artifact_id", None),
            getattr(state, "_show_app_settings", False),
            getattr(state, "_show_workspace_settings", False),
            len(state.artifacts),
        )
    ]

    @ui.refreshable
    def overlay_dialogs() -> None:
        render_command_palette(state)
        render_artifact_drawer(state)
        render_app_settings_modal(state)
        render_workspace_settings_modal(state)
        last_overlay_state[0] = (
            getattr(state, "_command_palette_open", False),
            getattr(state, "_selected_artifact_id", None),
            getattr(state, "_show_app_settings", False),
            getattr(state, "_show_workspace_settings", False),
            len(state.artifacts),
        )

    overlay_dialogs()

    def _on_overlay_check() -> None:
        cur = (
            getattr(state, "_command_palette_open", False),
            getattr(state, "_selected_artifact_id", None),
            getattr(state, "_show_app_settings", False),
            getattr(state, "_show_workspace_settings", False),
            len(state.artifacts),
        )
        if cur != last_overlay_state[0]:
            overlay_dialogs.refresh()

    state.subscribe(_on_overlay_check)
