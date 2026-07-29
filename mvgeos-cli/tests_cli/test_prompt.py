from __future__ import annotations

import pytest
from typer.testing import CliRunner

from mvgeos.commands.prompt import _build_spells, prompt_app

runner = CliRunner()


class TestPromptCommands:
    def test_prompt_app_exists(self) -> None:
        assert prompt_app is not None

    def test_build_spells(self) -> None:
        spells = _build_spells(["bash", "read", "write"])
        assert len(spells) == 3
        spell_names = [s.name for s in spells]
        assert "bash" in spell_names
        assert "read" in spell_names
        assert "write" in spell_names

    def test_build_spells_empty(self) -> None:
        spells = _build_spells([])
        assert len(spells) == 0

    def test_build_spells_invalid(self) -> None:
        spells = _build_spells(["invalid_spell"])
        assert len(spells) == 0


class TestPromptCommand:
    def test_prompt_no_api_key(self) -> None:
        result = runner.invoke(prompt_app, ["test prompt"])
        assert result.exit_code == 1
        assert "API key required" in result.output

    def test_prompt_unknown_model(self) -> None:
        result = runner.invoke(
            prompt_app,
            [
                "test prompt",
                "--model",
                "unknown-model",
                "--api-key",
                "test-key",
            ],
        )
        assert result.exit_code == 1
        assert "Unknown model" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
