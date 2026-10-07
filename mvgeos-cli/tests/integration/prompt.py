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
        """A Realm that needs a credential refuses, naming its own variable.

        ``google/`` rather than the default model: ``opencode`` is exempt from
        the credential requirement because its free tier serves without one, so
        on the default model this exits 0 now -- correctly, since there is no key
        to go and set. That behaviour is pinned separately, in ``cli.py``.
        """
        env = dict(os.environ)
        for name in ("OPENROUTER_API_KEY", "OPENCODE_API_KEY", "GEMINI_API_KEY"):
            env.pop(name, None)
        env.pop("GOOGLE_API_KEY", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("mvgeos_cli.main.load_api_key_for_realm", return_value=None),
        ):
            result = runner.invoke(
                app,
                ["--model", "google/gemini-2.5-flash", "--incantation", "test prompt"],
            )
            assert result.exit_code != 0
            assert "GOOGLE_API_KEY" in result.output

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
