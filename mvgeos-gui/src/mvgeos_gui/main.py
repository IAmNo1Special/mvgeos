"""CLI entry point for mvgeos-gui."""

import argparse
import asyncio
import contextlib
import ctypes
import importlib.metadata
import importlib.util
import logging
import os
import platform
import secrets
import sys
import threading
from pathlib import Path
from types import ModuleType

from nicegui import app, ui

from mvgeos_gui.app import init_app
from mvgeos_gui.core.logging import install_crash_handlers, setup_logging
from mvgeos_gui.services.config_service import ConfigService
from mvgeos_gui.state import ServerState

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
APP_TITLE = "MvgeOS"
_STORAGE_SECRET_FILE = Path.home() / ".mvgeos" / ".storage_secret"

# importlib-level handle for pywebview. Resolving the spec executes only the
# import finders, never the module itself, so no GUI backend is probed here.
_WEBVIEW_SPEC = importlib.util.find_spec("webview")


def _load_webview() -> ModuleType | None:
    """Load pywebview on first use, probing GUI backends only then.

    Prefers an already-imported ``webview`` module (e.g. pulled in by a
    dependency); otherwise executes the module from its spec. Returns None
    when pywebview is unavailable or fails to initialize, so callers fall
    back to default geometry instead of crashing.
    """
    module = sys.modules.get("webview")
    if module is not None:
        return module
    if _WEBVIEW_SPEC is None or _WEBVIEW_SPEC.loader is None:
        return None
    module = importlib.util.module_from_spec(_WEBVIEW_SPEC)
    sys.modules["webview"] = module
    try:
        _WEBVIEW_SPEC.loader.exec_module(module)
    except Exception:
        sys.modules.pop("webview", None)
        return None
    return module


def _shutdown_thread_excepthook(args: threading.ExceptHookArgs) -> None:
    """Suppress benign shutdown exceptions in background daemon threads.

    Non-benign thread exceptions are logged with a traceback so a dying
    background thread leaves a trace in the GUI log, then delegated to
    the default hook as before.
    """
    if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
        return
    thread_name = getattr(args.thread, "name", "") or ""
    if "check_shutdown" in thread_name:
        return
    crash_log = logging.getLogger("mvgeos_gui.crash")
    if args.exc_value is None:
        crash_log.error(
            "Uncaught %s in thread %r (no exception value)",
            args.exc_type.__name__,
            thread_name,
        )
    else:
        crash_log.error(
            "Uncaught exception in thread %r",
            thread_name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
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

    pywebview is loaded lazily through :func:`_load_webview`: importing it at
    module load would probe for GUI backends (GTK/Qt) even in --web mode,
    which can abort the process on machines where a backend partially
    initializes without a display.

    Returns:
        tuple[int, int, int | None, int | None]: (width, height, x, y)
    """
    webview = _load_webview()
    if webview is None:
        return target_width, target_height, None, None
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


def enable_windows_dark_titlebar(title: str = APP_TITLE, dark: bool = True) -> bool:
    """Apply the immersive titlebar theme to the Windows native titlebar.

    :param dark: True for the dark titlebar, False for the light one.
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
            value = ctypes.c_int(1 if dark else 0)
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


def _gui_version() -> str:
    """Return the installed mvgeos-gui version, or "unknown"."""
    try:
        return importlib.metadata.version("mvgeos-gui")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def main() -> None:
    """Main entry point function for mvgeos-gui console script."""
    args = parse_args()
    # Logging was previously never wired at entry: setup_logging() existed
    # but nothing called it, so the rotating mvgeos-gui.log file was never
    # written and uncaught deaths left no trace. Wire it first, then the
    # crash/shutdown diagnostics, before any app code can fail.
    logger = setup_logging()
    install_crash_handlers(logger)
    logger.info(
        "mvgeos-gui starting pid=%d version=%s mode=%s host=%s port=%d project=%s",
        os.getpid(),
        _gui_version(),
        "web" if args.web else "native",
        args.host,
        args.port,
        args.project,
    )
    server = ServerState(
        project_path=args.project,
        selected_model=args.model,
        api_key=args.api_key,
    )
    init_app(server)

    # Window placement is a native-mode concern only. Probing the display in
    # web mode would needlessly touch pywebview's GUI backends.
    width, height, x, y = (1400, 900, None, None)
    if not args.web:
        width, height, x, y = calculate_initial_window_geometry()

    # The native window chrome (pywebview background, Windows DWM
    # titlebar) renders before any page exists, so it follows the persisted
    # theme read here rather than waiting for inject_theme().
    saved_theme = ConfigService().load_app_settings().theme
    use_dark_chrome = saved_theme != "light"

    if not args.web:
        app.native.window_args["background_color"] = (
            "#000000" if use_dark_chrome else "#ffffff"
        )
        app.native.window_args["min_size"] = (800, 500)
        if x is not None:
            app.native.window_args["x"] = x
        if y is not None:
            app.native.window_args["y"] = y

        if platform.system() == "Windows":

            async def _apply_dark_titlebar() -> None:
                for _ in range(20):  # up to ~2 seconds
                    if enable_windows_dark_titlebar(APP_TITLE, dark=use_dark_chrome):
                        return
                    await asyncio.sleep(0.1)

            app.on_startup(_apply_dark_titlebar)

    def _cleanup() -> None:
        logger.info("mvgeos-gui shutdown initiated")
        # Fail closed for every connected client: pending approval casts
        # are denied, agent tasks cancelled, UI listeners dropped.
        server.shutdown()

    app.on_shutdown(_cleanup)

    with contextlib.suppress(KeyboardInterrupt):
        # BUG-5: NiceGUI 3.x treats any window_size as native mode, so in web
        # mode the keyword must be omitted entirely -- passing it spawns an
        # unwanted pywebview window next to the browser tab.
        run_kwargs = {
            "native": not args.web,
            "host": args.host,
            "port": args.port,
            "title": APP_TITLE,
            "reload": args.reload,
            "dark": use_dark_chrome,
            "reconnect_timeout": 60.0,
            "storage_secret": _get_storage_secret(),
        }
        if not args.web:
            run_kwargs["window_size"] = (width, height)
        try:
            ui.run(**run_kwargs)
        except Exception:
            # The server entry is wrapped so an uncaught exception lands in
            # the GUI log with a full traceback before propagating (the
            # sys.excepthook + atexit handlers then record the shutdown).
            logger.exception("mvgeos-gui server crashed with an uncaught exception")
            raise
    _cleanup()


if __name__ == "__main__":
    main()
