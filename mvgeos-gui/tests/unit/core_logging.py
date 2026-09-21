"""Unit tests for logging configuration."""

from __future__ import annotations

import faulthandler
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from mvgeos_gui.core.logging import (
    get_logger,
    install_crash_handlers,
    setup_logging,
)


def test_setup_logging_idempotent_when_handlers_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "gui_logs"
    monkeypatch.setenv("MVGEOS_LOG_DIR", str(log_dir))
    monkeypatch.setenv("MVGEOS_LOG_LEVEL", "DEBUG")

    logger = setup_logging()
    assert logger.name == "mvgeos_gui"
    assert log_dir.is_dir()


def test_setup_logging_configures_root_when_no_handlers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "fresh_logs"
    monkeypatch.setenv("MVGEOS_LOG_DIR", str(log_dir))
    monkeypatch.setenv("MVGEOS_LOG_LEVEL", "INFO")
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    root.handlers.clear()
    try:
        logger = setup_logging()
        assert logger.name == "mvgeos_gui"
        assert len(root.handlers) == 2
    finally:
        for h in root.handlers:
            h.close()
        root.handlers = old_handlers


def test_get_logger() -> None:
    child = get_logger("my_component")
    assert child.name == "mvgeos_gui.my_component"


def test_log_dir_and_file_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from mvgeos_gui.core.logging import _log_dir, _log_file, _resolve_level

    monkeypatch.delenv("MVGEOS_LOG_DIR", raising=False)
    monkeypatch.delenv("MVGEOS_LOG_LEVEL", raising=False)
    d = _log_dir()
    assert d.name == "logs"
    f = _log_file()
    assert f.name == "mvgeos-gui.log"
    lvl = _resolve_level()
    assert lvl == logging.INFO


def _run_crash_child(tmp_path: Path, script: str) -> subprocess.CompletedProcess[str]:
    """Run a fresh interpreter that installs crash handlers, then exits.

    A fresh process is the only honest way to observe excepthook/atexit
    behavior end to end.
    """
    env = dict(os.environ)
    env["MVGEOS_LOG_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _log_text(tmp_path: Path) -> str:
    return (tmp_path / "mvgeos-gui.log").read_text(encoding="utf-8")


def test_crash_handlers_write_startup_and_shutdown_records(
    tmp_path: Path,
) -> None:
    """A clean exit leaves both a startup record (with PID) and a shutdown record."""
    script = (
        "from mvgeos_gui.core.logging import setup_logging, install_crash_handlers;"
        "log = setup_logging();"
        "install_crash_handlers(log);"
        "log.info('marker-child-ready')"
    )
    proc = _run_crash_child(tmp_path, script)
    assert proc.returncode == 0, proc.stderr
    content = _log_text(tmp_path)
    assert "marker-child-ready" in content
    assert "pid=" in content
    assert "shutdown" in content
    assert "clean exit" in content


def test_excepthook_logs_uncaught_exception_with_traceback(
    tmp_path: Path,
) -> None:
    """An uncaught exception lands in the log with a traceback, and the
    shutdown record names the reason."""
    script = (
        "from mvgeos_gui.core.logging import setup_logging, install_crash_handlers;"
        "log = setup_logging();"
        "install_crash_handlers(log);"
        "raise RuntimeError('subprocess-boom-123')"
    )
    proc = _run_crash_child(tmp_path, script)
    assert proc.returncode != 0
    content = _log_text(tmp_path)
    assert "Uncaught exception" in content
    assert "subprocess-boom-123" in content
    assert "Traceback" in content
    assert "uncaught exception" in content


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics required")
def test_signal_handler_logs_sigterm_before_exit(tmp_path: Path) -> None:
    """SIGTERM is logged with its name before the process dies by the signal."""
    script = (
        "import os, signal;"
        "from mvgeos_gui.core.logging import setup_logging, install_crash_handlers;"
        "log = setup_logging();"
        "install_crash_handlers(log);"
        "log.info('marker-child-armed');"
        "os.kill(os.getpid(), signal.SIGTERM)"
    )
    proc = _run_crash_child(tmp_path, script)
    assert proc.returncode == -signal.SIGTERM
    content = _log_text(tmp_path)
    assert "marker-child-armed" in content
    assert "Received SIGTERM" in content


def test_install_crash_handlers_enables_faulthandler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """faulthandler is enabled so fatal signals dump thread tracebacks."""
    monkeypatch.setenv("MVGEOS_LOG_DIR", str(tmp_path))
    install_crash_handlers()
    assert faulthandler.is_enabled()
