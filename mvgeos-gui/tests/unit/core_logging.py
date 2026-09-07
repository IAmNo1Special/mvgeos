"""Unit tests for logging configuration."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mvgeos_gui.core.logging import get_logger, setup_logging


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
