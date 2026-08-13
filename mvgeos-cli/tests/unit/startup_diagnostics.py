from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_runes.types import Diagnostic, DiagnosticKind, RuneScope

from mvgeos_cli.commands.repl import _check_and_warn_load_failures, run_repl
from mvgeos_cli.commands.tui import run_tui


class TestStartupDiagnostics:
    def test_check_and_warn_load_failures_emits_warning(self) -> None:
        diags = [
            Diagnostic(
                kind=DiagnosticKind.LOAD_FAILURE,
                rune_name="seeker",
                message="missing dependency foo",
                scope=RuneScope.USER,
            ),
            Diagnostic(
                kind=DiagnosticKind.PARSE_WARNING,
                rune_name="other_rune",
                message="unknown key in config",
                scope=RuneScope.PROJECT,
            ),
        ]

        messages: list[str] = []
        _check_and_warn_load_failures(diags, out=messages.append)

        assert len(messages) > 0
        output = "\n".join(messages)
        assert "seeker" in output
        assert "missing dependency foo" in output
        assert "other_rune" not in output

    def test_check_and_warn_load_failures_no_load_failures(self) -> None:
        diags = [
            Diagnostic(
                kind=DiagnosticKind.PARSE_WARNING,
                rune_name="other_rune",
                message="unknown key in config",
                scope=RuneScope.PROJECT,
            )
        ]

        messages: list[str] = []
        _check_and_warn_load_failures(diags, out=messages.append)
        assert len(messages) == 0

    @pytest.mark.asyncio
    @patch("mvgeos_cli.commands.repl._create_agent")
    @patch("mvgeos_cli.commands.repl._read_initial_prompt")
    @patch("mvgeos_cli.commands.repl.PromptSession")
    async def test_run_repl_warns_on_startup_load_failure(
        self,
        mock_session_cls: MagicMock,
        mock_read_prompt: MagicMock,
        mock_create_agent: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_agent = AsyncMock()
        mock_agent.on = MagicMock(return_value=lambda: None)
        mock_agent.session_id = "test-session-id"
        mock_agent._model_id = "nvidia/nemotron"

        mock_env = MagicMock()
        mock_env.diagnostics = [
            Diagnostic(
                kind=DiagnosticKind.LOAD_FAILURE,
                rune_name="heal_my_goap",
                message="failed to import module",
                scope=RuneScope.PROJECT,
            )
        ]
        mock_agent.environment = mock_env
        mock_create_agent.return_value = mock_agent

        mock_read_prompt.return_value = None  # immediately exit REPL

        await run_repl(api_key="sk-or-test-key")

        captured = capsys.readouterr()
        assert "heal_my_goap" in captured.out
        assert "failed to import module" in captured.out

    @pytest.mark.asyncio
    @patch("mvgeos_cli.commands.tui._create_agent")
    @patch("mvgeos_cli.commands.tui.TuiApp")
    async def test_run_tui_warns_on_startup_load_failure(
        self,
        mock_tui_app_cls: MagicMock,
        mock_create_agent: MagicMock,
    ) -> None:
        mock_agent = AsyncMock()
        mock_agent.on = MagicMock(return_value=lambda: None)
        mock_env = MagicMock()
        mock_env.diagnostics = [
            Diagnostic(
                kind=DiagnosticKind.LOAD_FAILURE,
                rune_name="seeker",
                message="seeker error",
                scope=RuneScope.USER,
            )
        ]
        mock_agent.environment = mock_env
        mock_create_agent.return_value = mock_agent

        mock_app = MagicMock()
        mock_app.run = AsyncMock()
        mock_tui_app_cls.return_value = mock_app

        await run_tui(api_key="sk-or-test-key")

        # Verify app._out was called with the load failure warning
        assert mock_app._out.called
        call_texts = [call.args[0] for call in mock_app._out.call_args_list]
        combined = "\n".join(call_texts)
        assert "seeker" in combined
        assert "seeker error" in combined
