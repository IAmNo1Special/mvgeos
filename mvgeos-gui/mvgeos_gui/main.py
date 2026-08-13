"""CLI entry point for mvgeos-gui."""

import argparse
import asyncio
import contextlib
import ctypes
import sys
from pathlib import Path

from nicegui import app, ui

from mvgeos_gui.app import init_app
from mvgeos_gui.state import AppState

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
APP_TITLE = "MvgeOS"


def enable_windows_dark_titlebar(title: str = APP_TITLE) -> None:
    """Apply immersive dark mode to Windows native titlebar."""
    if sys.platform != "win32":
        return
    with contextlib.suppress(Exception):
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            dwmwa_use_immersive_dark_mode = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
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
    )
    init_app(state)

    if not args.web and sys.platform == "win32":
        app.native.window_args["background_color"] = "#181a20"

        async def _apply_dark_titlebar() -> None:
            await asyncio.sleep(0.3)
            enable_windows_dark_titlebar(APP_TITLE)

        app.on_startup(_apply_dark_titlebar)

    ui.run(
        native=not args.web,
        host=args.host,
        port=args.port,
        title=APP_TITLE,
        window_size=(1400, 900),
        reload=args.reload,
        dark=True,
    )


if __name__ == "__main__":
    main()
