"""Unit tests for mvgeos-gui CLI entry point and argument parsing."""

import inspect
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nicegui import app as nicegui_app

import mvgeos_gui.main as main_module
from mvgeos_gui.main import (
    _shutdown_thread_excepthook,
    calculate_initial_window_geometry,
    enable_windows_dark_titlebar,
    main,
    parse_args,
)
from mvgeos_gui.services.config_service import AppSettings


@pytest.fixture(autouse=True)
def setup_cli_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "cli_test.db"
    monkeypatch.setenv("MVGEOS_DB_PATH", str(db_file))


def test_parse_args_defaults() -> None:
    """Verify default CLI arguments."""
    args = parse_args([])
    assert args.web is False
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.project == Path.cwd()
    assert args.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert args.reload is False


def test_parse_args_custom_values() -> None:
    """Verify parsing custom CLI arguments."""
    args = parse_args(
        [
            "--web",
            "--host",
            "0.0.0.0",
            "--port",
            "8080",
            "--project",
            "C:/test/path",
            "--model",
            "anthropic/claude-3-5-sonnet",
            "--api-key",
            "sk-test-cli-key",
            "--reload",
        ]
    )
    assert args.web is True
    assert args.host == "0.0.0.0"
    assert args.port == 8080
    assert args.project == Path("C:/test/path")
    assert args.model == "anthropic/claude-3-5-sonnet"
    assert args.api_key == "sk-test-cli-key"
    assert args.reload is True


def test_calculate_initial_window_geometry_large_screen() -> None:
    """Verify centered geometry calculation for a standard 1080p display."""
    screen_mock = MagicMock(width=1920, height=1080, x=0, y=0)
    with patch("webview.screens", [screen_mock]):
        w, h, x, y = calculate_initial_window_geometry()
        assert w == 1400
        assert h == 900
        assert x == (1920 - 1400) // 2
        assert y == (1080 - 900) // 2


def test_calculate_initial_window_geometry_small_screen() -> None:
    """Verify window shrinks and centers on smaller displays (e.g., 1280x800)."""
    screen_mock = MagicMock(width=1280, height=800, x=0, y=0)
    with patch("webview.screens", [screen_mock]):
        w, h, x, y = calculate_initial_window_geometry()
        assert w < 1280
        assert h < 800
        assert x == (1280 - w) // 2
        assert y == (800 - h) // 2
        assert x > 0
        assert y > 0


def test_calculate_initial_window_geometry_offset_screen() -> None:
    """Verify window centers properly on secondary display with non-zero origin."""
    screen_mock = MagicMock(width=1920, height=1080, x=1920, y=100)
    with patch("webview.screens", [screen_mock]):
        w, h, x, y = calculate_initial_window_geometry()
        assert w == 1400
        assert h == 900
        assert x == 1920 + (1920 - 1400) // 2
        assert y == 100 + (1080 - 900) // 2


def test_calculate_initial_window_geometry_fallback_when_no_screens() -> None:
    """Verify fallback geometry when screen detection returns empty list."""
    with patch("webview.screens", []):
        w, h, x, y = calculate_initial_window_geometry()
        assert w == 1400
        assert h == 900
        assert x is None
        assert y is None


def test_calculate_initial_window_geometry_fallback_on_error() -> None:
    """Verify fallback geometry when screen querying raises an exception."""
    mock_screens = MagicMock()
    mock_screens.__getitem__.side_effect = RuntimeError("Screen detection failed")
    with patch("webview.screens", mock_screens):
        w, h, x, y = calculate_initial_window_geometry()
        assert w == 1400
        assert h == 900
        assert x is None
        assert y is None


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.app.on_startup")
@patch("mvgeos_gui.main.platform.system", return_value="Windows")
def test_main_runs_native_by_default(
    mock_system: MagicMock, mock_on_startup: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Verify main launches native window when --web is not specified."""
    with patch("sys.argv", ["mvgeos-gui"]):
        main()
        mock_ui_run.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is True
        assert kwargs.get("title") == "MvgeOS"
        assert kwargs.get("port") == 8000
        assert kwargs.get("host") == "127.0.0.1"
        assert any(
            call.args[0].__name__ == "_apply_dark_titlebar"
            for call in mock_on_startup.call_args_list
        )


def _config_service_with_theme(theme: str) -> MagicMock:
    """A ConfigService double whose persisted settings carry ``theme``."""
    service = MagicMock()
    service.load_app_settings.return_value = AppSettings(theme=theme)
    return service


@pytest.mark.asyncio
@patch("mvgeos_gui.main.platform.system", return_value="Windows")
async def test_startup_hook_invokes_dark_titlebar(mock_system: MagicMock) -> None:
    """The on_startup hook applies the Windows titlebar theme for the persisted theme.

    Persisted dark -> DWM dark titlebar; persisted light -> DWM light titlebar.
    """
    for theme, expected_dark in (("dark", True), ("light", False)):
        with (
            patch("mvgeos_gui.main.ui.run"),
            patch("mvgeos_gui.main.app.on_startup") as mock_on_startup,
            patch("mvgeos_gui.main.enable_windows_dark_titlebar") as mock_dark,
            patch(
                "mvgeos_gui.main.ConfigService",
                return_value=_config_service_with_theme(theme),
            ),
            patch("sys.argv", ["mvgeos-gui"]),
        ):
            main()
            startup_callback = mock_on_startup.call_args_list[-1][0][0]
            await startup_callback()
            mock_dark.assert_called_with("MvgeOS", dark=expected_dark)


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.app.on_startup")
@patch("mvgeos_gui.main.platform.system", return_value="Windows")
def test_main_native_dark_theme_uses_black_chrome(
    mock_system: MagicMock, mock_on_startup: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Persisted dark theme -> black pywebview background, dark ui.run."""
    original_window_args = dict(nicegui_app.native.window_args)
    try:
        with (
            patch("sys.argv", ["mvgeos-gui"]),
            patch(
                "mvgeos_gui.main.ConfigService",
                return_value=_config_service_with_theme("dark"),
            ),
        ):
            main()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs["dark"] is True
        assert nicegui_app.native.window_args["background_color"] == "#000000"
    finally:
        nicegui_app.native.window_args.clear()
        nicegui_app.native.window_args.update(original_window_args)


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.app.on_startup")
@patch("mvgeos_gui.main.platform.system", return_value="Windows")
def test_main_native_light_theme_uses_white_chrome(
    mock_system: MagicMock, mock_on_startup: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Persisted light theme -> white pywebview background, light ui.run."""
    original_window_args = dict(nicegui_app.native.window_args)
    try:
        with (
            patch("sys.argv", ["mvgeos-gui"]),
            patch(
                "mvgeos_gui.main.ConfigService",
                return_value=_config_service_with_theme("light"),
            ),
        ):
            main()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs["dark"] is False
        assert nicegui_app.native.window_args["background_color"] == "#ffffff"
    finally:
        nicegui_app.native.window_args.clear()
        nicegui_app.native.window_args.update(original_window_args)


@patch("mvgeos_gui.main.ui.run")
def test_main_runs_web_mode(mock_ui_run: MagicMock) -> None:
    """Verify main launches browser web mode when --web is passed."""
    with patch("sys.argv", ["mvgeos-gui", "--web", "--port", "9090"]):
        main()
        mock_ui_run.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is False
        assert kwargs.get("port") == 9090


def test_enable_windows_dark_titlebar_safe() -> None:
    """Verify enable_windows_dark_titlebar runs without unhandled exceptions."""
    enable_windows_dark_titlebar("NonExistentWindow")


def test_shutdown_thread_excepthook() -> None:
    """Verify shutdown thread excepthook suppresses benign termination errors."""
    # Suppresses KeyboardInterrupt
    args_kb = threading.ExceptHookArgs(
        (KeyboardInterrupt, KeyboardInterrupt(), None, None)
    )
    _shutdown_thread_excepthook(args_kb)

    # Suppresses SystemExit
    args_exit = threading.ExceptHookArgs((SystemExit, SystemExit(), None, None))
    _shutdown_thread_excepthook(args_exit)

    # Suppresses check_shutdown thread errors
    dummy_thread = MagicMock()
    dummy_thread.name = "Thread-2 (check_shutdown)"
    args_check = threading.ExceptHookArgs(
        (RuntimeError, RuntimeError("cannot interrupt"), None, dummy_thread)
    )
    _shutdown_thread_excepthook(args_check)

    # Delegates normal errors to __excepthook__
    with patch("threading.__excepthook__") as mock_orig:
        normal_thread = MagicMock()
        normal_thread.name = "WorkerThread"
        args_normal = threading.ExceptHookArgs(
            (ValueError, ValueError("boom"), None, normal_thread)
        )
        _shutdown_thread_excepthook(args_normal)
        mock_orig.assert_called_once_with(args_normal)


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.app.on_shutdown")
@pytest.mark.asyncio
async def test_main_registers_shutdown_cleanup(
    mock_on_shutdown: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Verify main registers cleanup on shutdown that clears listeners."""
    with patch("sys.argv", ["mvgeos-gui", "--web"]):
        main()
        mock_on_shutdown.assert_called_once()
        cleanup_cb = mock_on_shutdown.call_args[0][0]
        # The cleanup is a coroutine: NiceGUI awaits async on_shutdown
        # handlers in App.stop() before uvicorn cancels pending tasks.
        assert inspect.iscoroutinefunction(cleanup_cb)
        # Calling cleanup callback shouldn't raise
        await cleanup_cb()


@patch("mvgeos_gui.main.ui.run")
def test_main_web_mode_passes_no_window_size(mock_ui_run: MagicMock) -> None:
    """BUG-5: --web must not pass window_size — NiceGUI forces native mode
    whenever window_size is set, spawning an unwanted pywebview window."""
    with patch("sys.argv", ["mvgeos-gui", "--web"]):
        main()
        mock_ui_run.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is False
        assert "window_size" not in kwargs


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.platform.system", return_value="Linux")
def test_main_native_mode_passes_window_size(
    mock_system: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Native mode still gets an explicit window size."""
    with patch("sys.argv", ["mvgeos-gui"]):
        main()
        mock_ui_run.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is True
        window_size = kwargs.get("window_size")
        assert isinstance(window_size, tuple)
        assert len(window_size) == 2


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.calculate_initial_window_geometry")
def test_main_web_mode_skips_window_geometry(
    mock_geometry: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Web mode must not touch pywebview: no screen probing, no native window."""
    with patch("sys.argv", ["mvgeos-gui", "--web", "--port", "9090"]):
        main()
        mock_geometry.assert_not_called()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is False
        assert "window_size" not in kwargs


@patch("mvgeos_gui.main.ui.run")
@patch("mvgeos_gui.main.calculate_initial_window_geometry")
def test_main_native_mode_calculates_window_geometry(
    mock_geometry: MagicMock, mock_ui_run: MagicMock
) -> None:
    """Native mode still probes the display for window placement."""
    mock_geometry.return_value = (1400, 900, None, None)
    with patch("sys.argv", ["mvgeos-gui"]):
        main()
        mock_geometry.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is True
        assert kwargs.get("window_size") == (1400, 900)


def test_no_inline_imports_in_main_module() -> None:
    """Every import statement in main.py lives at module top level.

    Project standard (AGENTS.md): no inline imports. The pywebview lazy
    load must go through top-level importlib machinery, never an import
    inside a function body.
    """
    import ast

    source = Path(main_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is not node and isinstance(
                    child, (ast.Import, ast.ImportFrom)
                ):
                    offenders.append(f"{node.name}:{child.lineno}")
    assert not offenders, f"inline imports found: {offenders}"


def test_geometry_uses_already_imported_webview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A webview already in sys.modules is reused without re-executing it."""
    import sys

    stub = MagicMock()
    stub.screens = [MagicMock(width=1920, height=1080, x=0, y=0)]
    monkeypatch.setitem(sys.modules, "webview", stub)
    w, h, x, y = calculate_initial_window_geometry()
    assert w == 1400
    assert h == 900
    assert x == (1920 - 1400) // 2
    assert y == (1080 - 900) // 2


def test_geometry_falls_back_when_webview_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No webview anywhere: geometry falls back instead of probing."""
    import sys

    monkeypatch.delitem(sys.modules, "webview", raising=False)
    monkeypatch.setattr(main_module, "_WEBVIEW_SPEC", None)
    w, h, x, y = calculate_initial_window_geometry()
    assert w == 1400
    assert h == 900
    assert x is None
    assert y is None


def _clear_root_handlers() -> list:
    """Temporarily strip root handlers so setup_logging() configures fresh.

    Returns the previous handlers for restoration by the caller.
    """
    import logging

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    root.handlers.clear()
    return old_handlers


def _restore_root_handlers(old_handlers: list) -> None:
    import logging

    root = logging.getLogger()
    for h in root.handlers:
        h.close()
    root.handlers = old_handlers


def test_main_writes_startup_banner_with_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() must wire logging at entry: the startup banner carries the PID."""
    import os

    monkeypatch.setenv("MVGEOS_LOG_DIR", str(tmp_path))
    old_handlers = _clear_root_handlers()
    try:
        with (
            patch("mvgeos_gui.main.ui.run"),
            patch("sys.argv", ["mvgeos-gui", "--web"]),
        ):
            main()
    finally:
        _restore_root_handlers(old_handlers)
    content = (tmp_path / "mvgeos-gui.log").read_text(encoding="utf-8")
    assert f"pid={os.getpid()}" in content
    assert "starting" in content


def test_main_logs_uncaught_server_exception_with_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception escaping ui.run must land in the log with a traceback,
    then propagate (exit code preserved)."""
    monkeypatch.setenv("MVGEOS_LOG_DIR", str(tmp_path))
    old_handlers = _clear_root_handlers()
    try:
        with (
            patch(
                "mvgeos_gui.main.ui.run",
                side_effect=RuntimeError("server-boom-xyz"),
            ),
            patch("sys.argv", ["mvgeos-gui", "--web"]),
            pytest.raises(RuntimeError, match="server-boom-xyz"),
        ):
            main()
    finally:
        _restore_root_handlers(old_handlers)
    content = (tmp_path / "mvgeos-gui.log").read_text(encoding="utf-8")
    assert "server-boom-xyz" in content
    assert "Traceback" in content
