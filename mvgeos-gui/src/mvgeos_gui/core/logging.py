"""Structured logging configuration for mvgeos-gui."""

from __future__ import annotations

import atexit
import faulthandler
import logging
import os
import signal
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any, TextIO

_LOG_DIR = "logs"
_LOG_FILE = "mvgeos-gui.log"
_DEFAULT_LEVEL = "INFO"
_LEVEL_ENV = "MVGEOS_LOG_LEVEL"

# Install-once state for install_crash_handlers().
_crash_handlers_installed = False
# Set by the excepthook / signal handlers so the atexit record can name why
# the process is going down. None means "clean exit" (so far).
_shutdown_reason: str | None = None
# faulthandler writes to the fd of this stream; it must stay open for the
# life of the process, hence the module-level reference.
_faulthandler_stream: TextIO | None = None


def _log_dir() -> Path:
    env_dir = os.environ.get("MVGEOS_LOG_DIR")
    if env_dir:
        return Path(env_dir)
    base = Path(__file__).resolve().parent.parent.parent
    return base / _LOG_DIR


def _log_file() -> Path:
    return _log_dir() / _LOG_FILE


def _resolve_level() -> int:
    env_level = os.environ.get(_LEVEL_ENV, _DEFAULT_LEVEL).upper()
    return getattr(logging, env_level, logging.INFO)


def setup_logging(level: int | None = None) -> logging.Logger:
    """Configure application-wide logging with rotating file and console handlers.

    Creates the log directory if it does not exist.  The file handler rotates
    daily and keeps 7 backups.  Console output goes to stderr.

    Call once at startup; subsequent calls are idempotent for the root logger.
    """
    if level is None:
        level = _resolve_level()

    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger("mvgeos_gui")

    root.setLevel(level)

    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    file_handler = TimedRotatingFileHandler(
        _log_file(),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    root.addHandler(console_handler)

    return logging.getLogger("mvgeos_gui")


def get_logger(name: str) -> logging.Logger:
    """Return a child logger namespaced under ``mvgeos_gui``."""
    return logging.getLogger(f"mvgeos_gui.{name}")


def install_crash_handlers(logger: logging.Logger | None = None) -> None:
    """Install last-resort crash and shutdown diagnostics.

    Idempotent: safe to call more than once.

    Installs, in order:

    - faulthandler, dumping all-thread tracebacks into the GUI log file on
      fatal signals (SIGSEGV, SIGABRT, SIGFPE, ...).
    - a ``sys.excepthook`` that logs uncaught exceptions with their
      tracebacks at CRITICAL, then chains to the default hook so the
      process exit code is preserved.
    - chained SIGTERM/SIGINT/SIGHUP handlers that record the signal name
      for the shutdown record, then delegate to the previously installed
      handler. Best effort: frameworks that manage their own signals
      (uvicorn under ``ui.run``) install their handlers later and take
      precedence; in that case the atexit shutdown record is the trace.
    - an atexit hook that always writes a shutdown record naming the
      reason: the received signal, "uncaught exception", "keyboard
      interrupt", or "clean exit".

    Forensic rule: a startup record with no matching shutdown record means
    the process died from outside and could leave no trace — SIGKILL (the
    OOM killer), power loss, or ``os._exit``. Nothing in-process can log
    those.
    """
    global _crash_handlers_installed
    log = logger if logger is not None else logging.getLogger("mvgeos_gui")
    _install_faulthandler(log)
    sys.excepthook = _crash_excepthook
    _install_signal_handlers(log)
    if not _crash_handlers_installed:
        atexit.register(_log_shutdown_record)
    _crash_handlers_installed = True


def _install_faulthandler(log: logging.Logger) -> None:
    """Point faulthandler at the GUI log file (stderr fallback)."""
    global _faulthandler_stream
    if _faulthandler_stream is None:
        try:
            _log_file().parent.mkdir(parents=True, exist_ok=True)
            # Intentionally long-lived: faulthandler writes to this fd on
            # fatal signals for the life of the process.
            _faulthandler_stream = open(  # noqa: SIM115
                _log_file(), "a", encoding="utf-8"
            )
        except OSError as exc:
            log.warning("faulthandler falling back to stderr: %s", exc)
    if _faulthandler_stream is not None:
        faulthandler.enable(file=_faulthandler_stream)
    else:
        faulthandler.enable()


def _crash_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    """Log uncaught exceptions with a traceback, then chain to default."""
    global _shutdown_reason
    if issubclass(exc_type, KeyboardInterrupt):
        _shutdown_reason = "keyboard interrupt"
    else:
        _shutdown_reason = "uncaught exception"
        logging.getLogger("mvgeos_gui.crash").critical(
            "Uncaught exception reached the interpreter",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _install_signal_handlers(log: logging.Logger) -> None:
    """Chain signal handlers that record the signal for the shutdown record."""
    for signame in ("SIGTERM", "SIGINT", "SIGHUP"):
        signum = getattr(signal, signame, None)
        if signum is None:
            continue
        try:
            previous = signal.getsignal(signum)
        except (OSError, ValueError):
            continue
        if previous is None:
            continue

        def _handler(
            num: int,
            frame: FrameType | None,
            _prev: Any = previous,
        ) -> None:
            global _shutdown_reason
            name = signal.Signals(num).name
            _shutdown_reason = f"signal {name}"
            log.warning("Received %s; shutting down", name)
            if callable(_prev):
                _prev(num, frame)
            elif _prev == signal.SIG_DFL:
                # Restore the default disposition and re-raise so the
                # process terminates *by* the signal, as it would have.
                signal.signal(num, signal.SIG_DFL)
                os.kill(os.getpid(), num)
            # SIG_IGN: nothing further to do.

        try:
            signal.signal(signum, _handler)
        except (OSError, ValueError, RuntimeError):
            # Not the main thread, or the platform refuses: skip.
            continue


def _log_shutdown_record() -> None:
    """Write the final shutdown record naming why the process is exiting."""
    reason = _shutdown_reason or "clean exit"
    logging.getLogger("mvgeos_gui").info(
        "mvgeos-gui shutdown pid=%d reason=%s", os.getpid(), reason
    )
