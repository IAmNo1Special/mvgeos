"""CLI entry point for mvgeos-gui."""

import argparse
import asyncio
import contextlib
import ctypes
import platform
from pathlib import Path

from nicegui import app, ui

from mvgeos_gui.app import init_app
from mvgeos_gui.state import AppState

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
APP_TITLE = "MvgeOS"


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
        import webview

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

    return min(target_width, 1200), min(target_height, 750), None, None


def enable_windows_dark_titlebar(title: str = APP_TITLE) -> None:
    """Apply immersive dark mode to Windows native titlebar."""
    if platform.system() != "Windows":
        return
    with contextlib.suppress(Exception):
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return
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
                await asyncio.sleep(0.3)
                enable_windows_dark_titlebar(APP_TITLE)

            app.on_startup(_apply_dark_titlebar)

    app.on_shutdown(state.stop_channeling)

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
        )
    state.stop_channeling()


if __name__ == "__main__":
    main()
