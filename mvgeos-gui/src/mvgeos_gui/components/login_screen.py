"""Login dialog for mvgeos-gui."""

from __future__ import annotations

from nicegui import ui

from mvgeos_gui.core.security import login_limiter
from mvgeos_gui.services.auth_service import AuthService
from mvgeos_gui.state import AppState


def render_login_screen(state: AppState) -> None:
    """Render the login dialog."""
    auth = getattr(state, "_auth_service", None) or AuthService()

    if state._show_app_settings:
        state._show_app_settings = False

    with (
        ui.dialog()
        .value(state._show_login)
        .on("close", state.hide_login)
        .props("maximized persistent"),
        ui.card().classes(
            "w-full max-w-sm bg-[#1e212b] border border-[#2b2f3d] rounded-xl p-8 gap-6"
        ),
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon("auto_awesome", size="28px").classes("text-[#3b82f6]")
            ui.label("MvgeOS").classes(
                "text-xl font-bold text-[#e6edf3] tracking-tight"
            )

        ui.label("Sign in to continue").classes("text-sm text-[#8b949e] -mt-2")

        username_input = (
            ui.input("Username", placeholder="Enter username")
            .classes("w-full")
            .props("outlined dense autogrow")
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
            user = auth.login(username, password)
            if user is None:
                error_label.set_text("Invalid username or password")
                return
            state._auth_service = auth
            state.current_user = user
            state.hide_login()
            state.notify()

        ui.button(
            "Sign In",
            on_click=_do_login,
        ).props("unelevated no-caps").classes(
            "w-full bg-[#3b82f6] hover:bg-blue-600 "
            "text-white font-medium py-2.5 rounded-lg"
        )

        ui.label("Default: admin / admin").classes("text-xs text-center text-[#64748b]")
