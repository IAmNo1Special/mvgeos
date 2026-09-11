from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mvgeos_provider import NoRealmRegisteredError
from typer.testing import CliRunner

from mvgeos_cli.main import _run_agent, app

runner = CliRunner()


def test_rune_help() -> None:
    result = runner.invoke(app, ["rune", "--help"])
    assert result.exit_code == 0
    assert "Extension rune management" in result.output
    assert "install" in result.output


def test_rune_install_success() -> None:
    with patch(
        "mvgeos_cli.commands.rune.install_rune",
        return_value=Path("/tmp/extensions/sample-rune"),
    ) as mock_install:
        result = runner.invoke(app, ["rune", "install", "sample-rune"])
        assert result.exit_code == 0
        assert "Successfully installed rune 'sample-rune'" in result.output
        mock_install.assert_called_once_with("sample-rune")


def test_rune_install_failure() -> None:
    with patch(
        "mvgeos_cli.commands.rune.install_rune",
        side_effect=ValueError("Rune 'bad-rune' not found in marketplace."),
    ):
        result = runner.invoke(app, ["rune", "install", "bad-rune"])
        assert result.exit_code == 1
        assert "Rune 'bad-rune' not found in marketplace." in result.output


@pytest.mark.asyncio
async def test_no_realm_registered_repl_prompt_accepted() -> None:
    call_count = 0

    async def fake_repl(**kwargs: object) -> int:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise NoRealmRegisteredError(
                "No Realm factory registered for model 'anthropic/claude-3-5-sonnet'. "
                "Run 'mvgeos rune install openrouter-realm' to install it from "
                "the central marketplace."
            )
        return 0

    with (
        patch("mvgeos_cli.main.run_repl", side_effect=fake_repl),
        patch("builtins.input", return_value="y") as mock_input,
        patch("mvgeos_cli.main.install_rune") as mock_install,
    ):
        code = await _run_agent(
            incantation=None,
            model_id="anthropic/claude-3-5-sonnet",
            api_key="sk-or-test",
            temperature=None,
            max_tokens=None,
            contemplation_level=None,
            spells_enabled=None,
            extension_dir=None,
            resume=None,
            provider_name=None,
            tome_dir=None,
            tui=False,
            prompts=[],
        )

        assert code == 0
        assert call_count == 2
        mock_input.assert_called_once()
        mock_install.assert_called_once_with("openrouter-realm")


@pytest.mark.asyncio
async def test_no_realm_registered_repl_prompt_rejected() -> None:
    async def fake_repl(**kwargs: object) -> int:
        raise NoRealmRegisteredError(
            "No Realm factory registered for model 'anthropic/claude-3-5-sonnet'."
        )

    with (
        patch("mvgeos_cli.main.run_repl", side_effect=fake_repl),
        patch("builtins.input", return_value="n") as mock_input,
        patch("mvgeos_cli.main.install_rune") as mock_install,
    ):
        code = await _run_agent(
            incantation=None,
            model_id="anthropic/claude-3-5-sonnet",
            api_key="sk-or-test",
            temperature=None,
            max_tokens=None,
            contemplation_level=None,
            spells_enabled=None,
            extension_dir=None,
            resume=None,
            provider_name=None,
            tome_dir=None,
            tui=False,
            prompts=[],
        )

        assert code == 1
        mock_input.assert_called_once()
        mock_install.assert_not_called()


@pytest.mark.asyncio
async def test_no_realm_registered_print_mode_no_prompt() -> None:
    with (
        patch(
            "mvgeos_cli.main._create_agent",
            side_effect=NoRealmRegisteredError("No Realm factory registered."),
        ),
        patch("builtins.input") as mock_input,
    ):
        code = await _run_agent(
            incantation="test incantation",
            model_id="openai/gpt-4o",
            api_key="sk-or-test",
            temperature=None,
            max_tokens=None,
            contemplation_level=None,
            spells_enabled=None,
            extension_dir=None,
            resume=None,
            provider_name=None,
            tome_dir=None,
            tui=False,
            prompts=["hello"],
        )

        assert code == 1
        mock_input.assert_not_called()
