"""Login dialog for mvgeos-gui."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.core.security import login_limiter
from mvgeos_gui.services.auth_service import AuthService
from mvgeos_gui.state import AppState


def render_login_screen(state: AppState) -> None:
    """Render the login dialog."""
    if not getattr(state, "_show_login", False):
        return

    auth = getattr(state, "_auth_service", None) or AuthService()

    if state._show_app_settings:
        state.close_app_settings()

    with (
        ui.dialog().on("close", state.hide_login) as dialog,
        ui.card().classes(
            "w-full max-w-sm bg-[#0e0e12] border border-[#292335] rounded-xl p-8 gap-6"
        ),
    ):

        def _close_dialog() -> None:
            state.hide_login()
            dialog.close()

        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("auto_awesome", size="28px").classes("text-[#7b6cf6]")
                ui.label("MvgeOS").classes(
                    "text-xl font-bold text-[#eceaf4] tracking-tight"
                )
            ui.button(
                icon="close",
                on_click=_close_dialog,
            ).props("flat round dense").classes(
                "text-[#9c94b3] hover:text-white -mr-2"
            ).mark("close_login_btn")

        ui.label("Sign in to continue").classes("text-sm text-[#9c94b3] -mt-2")

        username_input = (
            ui.input("Username", placeholder="Enter username")
            .classes("w-full")
            .props("outlined dense")
        )

        password_input = (
            ui.input("Password", placeholder="Enter password", password=True)
            .classes("w-full")
            .props("outlined dense")
        )

        error_label = ui.label("").classes("text-xs text-red-400")

        def _do_login() -> None:
            username = username_input.value.strip()
            password = password_input.value
            if not username or not password:
                error_label.set_text("Enter both username and password")
                return
            if login_limiter.is_locked(username):
                error_label.set_text("Too many attempts. Try again later.")
                return
            try:
                user = auth.login(username, password)
            except Exception as exc:
                error_label.set_text(f"Login error: {exc}")
                return
            if user is None:
                error_label.set_text("Invalid username or password")
                return
            state._auth_service = auth
            state.current_user = user
            state.hide_login()
            state.notify()

        password_input.on("keydown.enter", lambda _e: _do_login())

        ui.button(
            "Sign In",
            on_click=_do_login,
        ).props("unelevated no-caps").classes(
            "w-full mvge-glow-btn text-white font-medium py-2.5 rounded-lg"
        )

    dialog.open()
