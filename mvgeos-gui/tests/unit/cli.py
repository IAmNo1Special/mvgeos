"""Unit tests for mvgeos-gui CLI entry point and argument parsing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from mvgeos_gui.main import main, parse_args


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
            "--reload",
        ]
    )
    assert args.web is True
    assert args.host == "0.0.0.0"
    assert args.port == 8080
    assert args.project == Path("C:/test/path")
    assert args.model == "anthropic/claude-3-5-sonnet"
    assert args.reload is True


@patch("mvgeos_gui.main.ui.run")
def test_main_runs_native_by_default(mock_ui_run: MagicMock) -> None:
    """Verify main launches native window when --web is not specified."""
    with patch("sys.argv", ["mvgeos-gui"]):
        main()
        mock_ui_run.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is True
        assert kwargs.get("title") == "Antigravity"
        assert kwargs.get("port") == 8000
        assert kwargs.get("host") == "127.0.0.1"


@patch("mvgeos_gui.main.ui.run")
def test_main_runs_web_mode(mock_ui_run: MagicMock) -> None:
    """Verify main launches browser web mode when --web is passed."""
    with patch("sys.argv", ["mvgeos-gui", "--web", "--port", "9090"]):
        main()
        mock_ui_run.assert_called_once()
        kwargs = mock_ui_run.call_args.kwargs
        assert kwargs.get("native") is False
        assert kwargs.get("port") == 9090
