from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mvgeos_cli.commands.repl import (
    NoConsoleScreenBufferError,
    _read_fallback_prompt,
    run_repl,
)
from mvgeos_cli.commands.tui import run_tui


class TestNoConsoleBufferFallback:
    @pytest.mark.asyncio
    async def test_read_fallback_prompt_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda prompt: "hello world")
        result = await _read_fallback_prompt()
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_fallback_prompt_keyboard_interrupt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_ki(prompt: str) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", raise_ki)
        result = await _read_fallback_prompt()
        assert result is None

    @pytest.mark.asyncio
    async def test_read_fallback_prompt_eof_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_eof(prompt: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        result = await _read_fallback_prompt()
        assert result is None

    @pytest.mark.asyncio
    @patch("mvgeos_cli.commands.repl._create_agent")
    @patch("mvgeos_cli.commands.repl.PromptSession")
    async def test_run_repl_instantiation_no_console_buffer(
        self,
        mock_session_cls: MagicMock,
        mock_create_agent: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_agent = AsyncMock()
        mock_agent.on = MagicMock(return_value=lambda: None)
        mock_agent.tome_id = "test-tome-id"
        mock_agent._model_id = "nvidia/nemotron"
        mock_create_agent.return_value = mock_agent

        # PromptSession creation raises NoConsoleScreenBufferError
        mock_session_cls.side_effect = NoConsoleScreenBufferError()

        inputs = ["/help", "/quit"]
        input_iter = iter(inputs)

        def mock_input(prompt: str = "") -> str:
            return next(input_iter)

        monkeypatch.setattr("builtins.input", mock_input)

        await run_repl(api_key="sk-or-test-key")

        mock_agent.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("mvgeos_cli.commands.repl._create_agent")
    @patch("mvgeos_cli.commands.repl._read_initial_prompt")
    @patch("mvgeos_cli.commands.repl.PromptSession")
    async def test_run_repl_lazy_prompt_no_console_buffer(
        self,
        mock_session_cls: MagicMock,
        mock_read_initial: MagicMock,
        mock_create_agent: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_agent = AsyncMock()
        mock_agent.on = MagicMock(return_value=lambda: None)
        mock_agent.tome_id = "test-tome-id"
        mock_agent._model_id = "nvidia/nemotron"
        mock_create_agent.return_value = mock_agent

        mock_session_cls.return_value = MagicMock()
        # _read_initial_prompt raises NoConsoleScreenBufferError on first prompt call
        mock_read_initial.side_effect = NoConsoleScreenBufferError()

        inputs = ["/quit"]
        input_iter = iter(inputs)

        def mock_input(prompt: str = "") -> str:
            return next(input_iter)

        monkeypatch.setattr("builtins.input", mock_input)

        await run_repl(api_key="sk-or-test-key")

        mock_agent.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("mvgeos_cli.commands.tui._create_agent")
    @patch("mvgeos_cli.commands.tui.TuiApp")
    async def test_run_tui_no_console_buffer(
        self,
        mock_tui_app_cls: MagicMock,
        mock_create_agent: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_agent = AsyncMock()
        mock_agent.on = MagicMock(return_value=lambda: None)
        mock_create_agent.return_value = mock_agent

        mock_app = MagicMock()
        mock_app.run = AsyncMock(side_effect=NoConsoleScreenBufferError())
        mock_tui_app_cls.return_value = mock_app

        await run_tui(api_key="sk-or-test-key")

        captured = capsys.readouterr()
        assert "TUI mode requires a Win32 console screen buffer" in captured.out
        mock_agent.close.assert_awaited_once()
