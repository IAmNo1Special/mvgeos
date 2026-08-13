from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from mvgeos_cli.commands.build import build_app
from mvgeos_cli.commands.config import config_app
from mvgeos_cli.commands.info import info_app
from mvgeos_cli.commands.setup import setup_app
from mvgeos_cli.main import app

runner = CliRunner()
FAKE_AGENT = "totally-fake-unknown-agent-999"


def _has_error(result: Any, text: str) -> bool:
    output = result.output or ""
    exc = str(result.exception) if result.exception is not None else ""
    return text in output or text in exc


def test_main_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(app, ["--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_build_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(build_app, ["--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_info_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(info_app, ["--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_config_show_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(config_app, ["show", "--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_config_get_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(config_app, ["get", "model", "--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_config_reset_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(config_app, ["reset", "--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_config_path_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(config_app, ["path", "--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_setup_check_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(setup_app, ["check", "--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_setup_install_unknown_agent_name_exits_with_error() -> None:
    result = runner.invoke(setup_app, ["install", "--agent-name", FAKE_AGENT])
    assert result.exit_code != 0
    assert _has_error(result, "Unknown agent") or _has_error(result, FAKE_AGENT)


def test_path_traversal_agent_name_exits_with_error() -> None:
    result = runner.invoke(build_app, ["--agent-name", "../etc/passwd"])
    assert result.exit_code != 0
    assert _has_error(result, "Invalid agent name")


def test_default_agent_name_succeeds() -> None:
    result = runner.invoke(config_app, ["show", "--agent-name", "default-mvge"])
    assert result.exit_code == 0
