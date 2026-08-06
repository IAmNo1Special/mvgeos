from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mvgeos_cli.main import app

runner = CliRunner()


class TestPromptCommands:
    def test_prompt_app_exists(self) -> None:
        # Test that the prompt command exists in the main app
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "incantation" in result.output.lower()

    def test_build_spells(self) -> None:
        # Test the internal function if exposed, or skip
        pass


class TestPromptCommand:
    def test_prompt_no_api_key(self) -> None:
        # Ensure OPENROUTER_API_KEY is not set and no auth file exists
        env = dict(os.environ)
        env.pop("OPENROUTER_API_KEY", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("mvgeos_cli.main._load_api_key_from_auth", return_value=None),
        ):
            result = runner.invoke(app, ["--incantation", "test prompt"])
            assert result.exit_code != 0

    def test_prompt_unknown_model(self) -> None:
        result = runner.invoke(
            app,
            [
                "--incantation",
                "test prompt",
                "--model",
                "unknown-model",
                "--api-key",
                "test-key",
            ],
        )
        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
