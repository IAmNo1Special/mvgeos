"""Structured logging configuration for mvgeos-gui."""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_LOG_DIR = "logs"
_LOG_FILE = "mvgeos-gui.log"
_DEFAULT_LEVEL = "INFO"
_LEVEL_ENV = "MVGEOS_LOG_LEVEL"


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
