from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from mvgeos_cli.commands.repl import _create_agent
from mvgeos_cli.main import _get_session_dir, _run_agent, app

runner = CliRunner()


def test_main_is_callable() -> None:
    from mvgeos_cli.main import main

    assert callable(main)


def test_get_session_dir() -> None:
    path = _get_session_dir()
    assert path == Path.home() / ".agents" / ".mvgeos" / "tomes"


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


def test_app_build_help() -> None:
    result = runner.invoke(app, ["build", "--help"])
    assert result.exit_code == 0
    assert "manifest" in result.output.lower()


def test_app_info_help() -> None:
    result = runner.invoke(app, ["info", "--help"])
    assert result.exit_code == 0
    assert "snapshot" in result.output.lower()


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_repl_callback_no_incantation_runs_repl(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_repl_callback_with_incantation(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(app, ["--incantation", "hello world"])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()
    call_kwargs = mock_run_agent.call_args[1]
    assert call_kwargs["incantation"] == "hello world"


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_repl_callback_with_options(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(
        app,
        [
            "--model",
            "test/model",
            "--temperature",
            "0.5",
            "--max-tokens",
            "2048",
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
    assert call_kwargs["contemplation_level"] == "high"
    assert call_kwargs["spells_enabled"] == ["bash", "read"]
    assert call_kwargs["extension_dir"] == "/tmp/ext"
    assert call_kwargs["resume"] == "/tmp/session.jsonl"
    assert call_kwargs["provider_name"] == "test-provider"
    assert call_kwargs["session_dir"] == "/tmp/sessions"
    assert call_kwargs["tui"] is True


def test_repl_callback_missing_api_key() -> None:
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    with (
        patch.dict(os.environ, env, clear=True),
        patch("mvgeos_cli.main._load_api_key_from_auth", return_value=None),
    ):
        result = runner.invoke(app, ["--incantation", "test"])
        assert result.exit_code == 1
        assert "API key required" in result.output


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_one_shot_merges_incantation_and_positionals(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(app, ["--incantation", "p0", "p1", "p2"])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()
    call_kwargs = mock_run_agent.call_args[1]
    assert call_kwargs["incantation"] == "p0"
    assert call_kwargs["prompts"] == ["p1", "p2"]


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_one_shot_positional_only(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(app, ["list", "files"])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()
    call_kwargs = mock_run_agent.call_args[1]
    assert call_kwargs["incantation"] is None
    assert call_kwargs["prompts"] == ["list", "files"]


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_subcommands_still_route(mock_run_agent: AsyncMock) -> None:
    result = runner.invoke(app, ["tome", "list"])
    assert result.exit_code == 0
    mock_run_agent.assert_not_called()


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_options_after_positionals_are_prompts(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(app, ["p1", "--model", "x"])
    assert result.exit_code == 0
    mock_run_agent.assert_called_once()
    call_kwargs = mock_run_agent.call_args[1]
    assert call_kwargs["prompts"] == ["p1", "--model", "x"]


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_error_exit_code_propagates(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 1
    result = runner.invoke(app, ["p1"])
    assert result.exit_code == 1


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-test-key"})
@patch("mvgeos_cli.main._run_agent", new_callable=AsyncMock)
def test_success_exit_code_zero(mock_run_agent: AsyncMock) -> None:
    mock_run_agent.return_value = 0
    result = runner.invoke(app, ["p1"])
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_run_agent_closes_agent_on_error() -> None:
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("Agent failure"))
    mock_agent.close = AsyncMock()

    with patch(
        "mvgeos_cli.main._create_agent",
        new_callable=AsyncMock,
        return_value=mock_agent,
    ):
        code = await _run_agent(
            incantation="test",
            model_id=None,
            api_key="sk-or-v1-test-key",
            temperature=None,
            max_tokens=None,
            contemplation_level=None,
            spells_enabled=None,
            extension_dir=None,
            resume=None,
            provider_name=None,
            session_dir=None,
            tui=False,
        )

    assert code == 1
    mock_agent.close.assert_called_once()


@pytest.mark.asyncio
async def test_bug4_single_registry_and_rune_providers(tmp_path: Path) -> None:
    rune_dir = tmp_path / "test_rune"
    rune_dir.mkdir()
    manifest = {
        "name": "test_rune",
        "version": "0.1.0",
        "description": "Test rune registering provider",
        "entry_point": "index.py",
    }
    (rune_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    index_code = (
        "def rune_factory(api):\n"
        "    api.register_provider('custom_rune_prov', {'base_url': 'http://localhost'})\n"
    )
    (rune_dir / "index.py").write_text(index_code, encoding="utf-8")

    session_dir = tmp_path / "sessions"

    with (
        patch("mvgeos_provider.openrouter.OpenRouterRealm.stream"),
        patch("mvgeos_runes.watcher.RuneWatcher.start", new_callable=AsyncMock),
        patch("mvgeos_runes.watcher.RuneWatcher.stop", new_callable=AsyncMock),
    ):
        agent = await _create_agent(
            model="nvidia/nemotron-3-ultra-550b-a55b:free",
            api_key="sk-or-v1-test-key",
            spells="bash,read",
            extension_dir=str(tmp_path),
            session_dir=str(session_dir),
            resume=None,
            provider=None,
            temperature=0.7,
            max_tokens=4096,
            contemplation="medium",
        )
        try:
            assert "custom_rune_prov" in agent.registered_providers
            assert agent._state is not None
            assert agent._state.rune_runner is not None
        finally:
            await agent.close()
