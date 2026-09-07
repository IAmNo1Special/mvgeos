"""CLI entry point for mvgeos-gui."""

import argparse
import asyncio
import contextlib
import ctypes
import os
import platform
import secrets
import threading
from pathlib import Path

import webview
from nicegui import app, ui

from mvgeos_gui.app import init_app
from mvgeos_gui.state import AppState

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
APP_TITLE = "MvgeOS"
_STORAGE_SECRET_FILE = Path.home() / ".mvgeos" / ".storage_secret"


def _shutdown_thread_excepthook(args: threading.ExceptHookArgs) -> None:
    """Suppress benign shutdown exceptions in background daemon threads."""
    if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
        return
    thread_name = getattr(args.thread, "name", "") or ""
    if "check_shutdown" in thread_name:
        return
    threading.__excepthook__(args)


threading.excepthook = _shutdown_thread_excepthook


def _get_storage_secret() -> str:
    """Resolve the storage secret for NiceGUI signed cookies.

    Priority:
    1. ``STORAGE_SECRET`` environment variable
    2. Persisted secret file at ``~/.mvgeos/.storage_secret``
    3. Generate a new random secret and persist it
    """
    env_secret = os.environ.get("STORAGE_SECRET")
    if env_secret:
        return env_secret

    try:
        if _STORAGE_SECRET_FILE.exists():
            return _STORAGE_SECRET_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        pass

    _STORAGE_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_urlsafe(32)
    with contextlib.suppress(OSError):
        _STORAGE_SECRET_FILE.write_text(new_secret, encoding="utf-8")

    return new_secret


def calculate_initial_window_geometry(
    target_width: int = 1400,
    target_height: int = 900,
    min_width: int = 800,
    min_height: int = 500,
    max_screen_ratio_w: float = 0.90,
    max_screen_ratio_h: float = 0.88,
) -> tuple[int, int, int | None, int | None]:
    """Calculate centered window dimensions and coordinates based on primary display.

    Uses pywebview's cross-platform screens API (``webview.screens``) to determine
    the display resolution and center coordinates across Windows, macOS, and Linux.

    Returns:
        tuple[int, int, int | None, int | None]: (width, height, x, y)
    """
    try:
        screens = getattr(webview, "screens", None)
        if screens:
            primary = screens[0]
            screen_w = int(primary.width)
            screen_h = int(primary.height)
            screen_x = int(getattr(primary, "x", 0))
            screen_y = int(getattr(primary, "y", 0))

            if screen_w > 0 and screen_h > 0:
                # Cap dimensions to screen ratio to prevent bleeding off screen
                max_w = max(min_width, int(screen_w * max_screen_ratio_w))
                max_h = max(min_height, int(screen_h * max_screen_ratio_h))

                width = min(target_width, max_w)
                height = min(target_height, max_h)

                # Ensure width/height do not exceed physical screen
                width = min(width, screen_w)
                height = min(height, screen_h)

                x = screen_x + max(0, (screen_w - width) // 2)
                y = screen_y + max(0, (screen_h - height) // 2)
                return width, height, x, y
    except Exception:
        pass

    return target_width, target_height, None, None


def enable_windows_dark_titlebar(title: str = APP_TITLE) -> bool:
    """Apply immersive dark mode to Windows native titlebar.

    Returns True if the titlebar was found and updated, False otherwise.
    """
    if platform.system() != "Windows":
        return False
    with contextlib.suppress(Exception):
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        hwnd = windll.user32.FindWindowW(None, title)
        if hwnd:
            dwmwa_use_immersive_dark_mode = 20
            value = ctypes.c_int(1)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                dwmwa_use_immersive_dark_mode,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            return True
    return False


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for mvgeos-gui."""
    parser = argparse.ArgumentParser(
        prog="mvgeos-gui",
        description="Launch MvgeOS desktop GUI application.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=False,
        help="Serve to web browser instead of native desktop window.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on (default: 8000).",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Initial workspace directory path (default: current working directory).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Default model slug (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload on source file changes.",
    )
    return parser.parse_args(args)


def main() -> None:
    """Main entry point function for mvgeos-gui console script."""
    args = parse_args()
    state = AppState(
        project_path=args.project,
        selected_model=args.model,
        api_key=args.api_key,
    )
    init_app(state)

    width, height, x, y = calculate_initial_window_geometry()

    if not args.web:
        app.native.window_args["background_color"] = "#181a20"
        app.native.window_args["min_size"] = (800, 500)
        if x is not None:
            app.native.window_args["x"] = x
        if y is not None:
            app.native.window_args["y"] = y

        if platform.system() == "Windows":

            async def _apply_dark_titlebar() -> None:
                for _ in range(20):  # up to ~2 seconds
                    if enable_windows_dark_titlebar(APP_TITLE):
                        return
                    await asyncio.sleep(0.1)

            app.on_startup(_apply_dark_titlebar)

    def _cleanup() -> None:
        state.stop_channeling()
        state.clear_listeners()

    app.on_shutdown(_cleanup)

    with contextlib.suppress(KeyboardInterrupt):
        ui.run(
            native=not args.web,
            host=args.host,
            port=args.port,
            title=APP_TITLE,
            window_size=(width, height),
            reload=args.reload,
            dark=True,
            reconnect_timeout=60.0,
            storage_secret=_get_storage_secret(),
        )
    _cleanup()


if __name__ == "__main__":
    main()
