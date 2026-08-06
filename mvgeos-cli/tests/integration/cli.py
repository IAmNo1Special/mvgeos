from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from mvgeos_cli.main import _build_spells, _get_session_dir, app

runner = CliRunner()


def test_main_is_callable() -> None:
    from mvgeos_cli.main import main

    assert callable(main)


def test_get_session_dir() -> None:
    from pathlib import Path

    path = _get_session_dir()
    assert path == Path("~/.agents/.mvgeos/tomes")


def test_build_spells() -> None:
    spells = _build_spells(["bash", "read"])
    assert len(spells) == 2
    names = {s.name for s in spells}
    assert names == {"bash", "read"}


def test_build_spells_empty() -> None:
    spells = _build_spells([])
    assert len(spells) == 0


def test_build_spells_unknown() -> None:
    spells = _build_spells(["bash", "unknown", "read"])
    assert len(spells) == 2
    names = {s.name for s in spells}
    assert names == {"bash", "read"}


def test_app_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "MvgeOS" in result.output
    assert "REPL" in result.output


def test_app_config_help() -> None:
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    assert "config" in result.output.lower()


def test_app_tome_help() -> None:
    result = runner.invoke(app, ["tome", "--help"])
    assert result.exit_code == 0
    assert "tome" in result.output.lower()


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_repl_callback_no_incantation_runs_repl(mock_run_agent: AsyncMock) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_repl_callback_with_incantation(mock_run_agent: AsyncMock) -> None:
    result = runner.invoke(app, ["--incantation", "hello world"])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()
    # Check the incantation was passed
    call_kwargs = mock_run_agent.call_args[1]
    assert call_kwargs["incantation"] == "hello world"


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_repl_callback_with_options(mock_run_agent: AsyncMock) -> None:
    # Use --incantation option instead of positional argument
    result = runner.invoke(
        app,
        [
            "--model",
            "test/model",
            "--temperature",
            "0.5",
            "--max-tokens",
            "2048",
            "--mana",
            "5000",
            "--contemplation",
            "high",
            "--spells",
            "bash,read",
            "--extension-dir",
            "/tmp/ext",
            "--resume",
            "/tmp/session.jsonl",
            "--provider",
            "test-provider",
            "--session-dir",
            "/tmp/sessions",
            "--tui",
            "--incantation",
            "test prompt",
        ],
    )
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()
    call_kwargs = mock_run_agent.call_args[1]
    assert call_kwargs["model_id"] == "test/model"
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["max_tokens"] == 2048
    assert call_kwargs["mana_budget"] == 5000
    assert call_kwargs["contemplation_level"] == "high"
    assert call_kwargs["spells_enabled"] == ["bash", "read"]
    assert call_kwargs["extension_dir"] == "/tmp/ext"
    assert call_kwargs["resume"] == "/tmp/session.jsonl"
    assert call_kwargs["provider_name"] == "test-provider"
    assert call_kwargs["session_dir"] == "/tmp/sessions"
    assert call_kwargs["tui"] is True


def test_repl_callback_missing_api_key() -> None:
    # Ensure OPENROUTER_API_KEY is not set and no auth file exists
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        with patch("mvgeos_cli.main._load_api_key_from_auth", return_value=None):
            result = runner.invoke(app, ["--incantation", "test"])
            assert result.exit_code == 1
            assert "API key required" in result.output
