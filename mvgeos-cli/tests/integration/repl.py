from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mvgeos_agent.constants import DEFAULT_MODEL
from mvgeos_agent.mvge import Mvge
from mvgeos_agent.types import MvgeEvent, MvgeEventType
from mvgeos_provider.model_registry import ModelRegistry

from mvgeos_cli.commands.repl import ReplAction, _handle_command


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def agent() -> Mvge:
    return Mvge(api_key="test-key")


class TestSlashCommands:
    def test_help(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/help", agent, registry)
        assert result == ReplAction.CONTINUE

    def test_quit(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/quit", agent, registry)
        assert result == ReplAction.EXIT

    def test_exit(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/exit", agent, registry)
        assert result == ReplAction.EXIT

    def test_session(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/session", agent, registry)
        assert result == ReplAction.CONTINUE

    def test_model_no_args_lists_models(
        self,
        agent: Mvge,
        registry: ModelRegistry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _handle_command("/model", agent, registry)
        assert result == ReplAction.CONTINUE
        captured = capsys.readouterr()
        models = registry.list_all()
        assert len(models) > 0
        for m in models:
            assert m.id in captured.out

    def test_model_with_args(self, agent: Mvge, registry: ModelRegistry) -> None:
        target = registry.list_all()[0].id
        result = _handle_command(f"/model {target}", agent, registry)
        assert result == ReplAction.SWITCH_MODEL
        assert agent._model_id == target

    def test_model_invalid(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/model unknown/model", agent, registry)
        assert result == ReplAction.CONTINUE
        assert agent._model_id == DEFAULT_MODEL

    def test_spells_no_args(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/spells", agent, registry)
        assert result == ReplAction.CONTINUE

    def test_spells_with_args(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/spells bash,read,write", agent, registry)
        assert result == ReplAction.CONTINUE
        assert agent._spell_names == ["bash", "read", "write"]

    def test_new(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/new", agent, registry)
        assert result == ReplAction.NEW_SESSION

    def test_resume_with_args(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command(
            "/resume .agents/.mvgeos/tomes/test.jsonl", agent, registry
        )
        assert result == ReplAction.NEW_SESSION
        assert agent._tome_resume == ".agents/.mvgeos/tomes/test.jsonl"

    def test_resume_no_args(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/resume", agent, registry)
        assert result == ReplAction.CONTINUE

    def test_unknown_command(self, agent: Mvge, registry: ModelRegistry) -> None:
        result = _handle_command("/unknown", agent, registry)
        assert result == ReplAction.CONTINUE


class TestReplHelpers:
    def test_format_error_rate_limit_friendly(self) -> None:
        from mvgeos_agent.errors import RateLimitError

        from mvgeos_cli.console import format_error

        markup = format_error(RateLimitError("You are being rate limited"))
        assert "Rate limited by the provider" in markup
        assert "[yellow]" in markup

    def test_models_free_filter(
        self,
        agent: Mvge,
        registry: ModelRegistry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _handle_command("/models --free", agent, registry)
        assert result == ReplAction.CONTINUE
        captured = capsys.readouterr()
        for m in registry.list_all():
            if m.free:
                assert m.id in captured.out

    def test_render_live_rate_limit_countdown(self) -> None:
        import asyncio

        from mvgeos_agent.errors import RateLimitError

        from mvgeos_cli.commands.repl import _render_live_rate_limit

        outputs: list[str] = []

        async def dummy_sleep(sec: float) -> None:
            pass

        exc = RateLimitError("limited", retry_after=3)
        asyncio.run(
            _render_live_rate_limit(exc, out=outputs.append, sleep_fn=dummy_sleep)
        )
        assert len(outputs) == 3
        assert "Retry in 3s..." in outputs[0]
        assert "Retry in 2s..." in outputs[1]
        assert "Retry in 1s..." in outputs[2]

    def test_format_error_rate_limit_with_retry_after(self) -> None:
        from mvgeos_agent.errors import RateLimitError

        from mvgeos_cli.console import format_error

        markup = format_error(RateLimitError("limited", retry_after=5))
        assert "Try again in 5s" in markup

    def test_format_error_unknown_returns_red_error(self) -> None:
        from mvgeos_cli.console import format_error

        assert format_error(RuntimeError("boom")) == "[red]Error: boom[/red]"

    def test_format_error_auth_friendly(self) -> None:
        from mvgeos_agent.errors import AuthenticationError

        from mvgeos_cli.console import format_error

        markup = format_error(AuthenticationError("User not found"))
        assert "Authentication failed" in markup
        assert "OPENROUTER_API_KEY" in markup
        assert "[red]" in markup

    def test_bindings_create(self) -> None:
        from mvgeos_cli.commands.repl import _make_bindings

        bindings = _make_bindings()
        assert bindings is not None

    def test_format_tome_info_shows_cwd_model_and_mana(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mvgeos_cli.commands import repl as repl_mod
        from mvgeos_cli.commands.repl import _format_tome_info

        monkeypatch.setattr(repl_mod, "_format_cwd", lambda: "~/proj")

        class _State:
            mana_used = 9500

        agent = Mvge(api_key="test-key")
        agent._state = _State()  # type: ignore[attr-defined]
        info = _format_tome_info(agent, branch="main")
        parts = " ".join(text for _, text in info)
        assert "~/proj (main)" in parts
        assert "mana 9500" in parts
        assert "nvidia/nemotron" in parts

    def test_format_tome_info_reports_mana_used(
        self,
    ) -> None:
        from mvgeos_cli.commands.repl import _format_tome_info

        class _State:
            mana_used = 7500

        agent = Mvge(api_key="test-key")
        agent._state = _State()  # type: ignore[attr-defined]
        info = _format_tome_info(agent)
        parts = " ".join(text for _, text in info)
        assert "mana 7500" in parts

    def test_format_tome_info_without_state(self) -> None:
        from mvgeos_cli.commands.repl import _format_tome_info

        agent = Mvge(api_key="test-key")
        info = _format_tome_info(agent)
        parts = " ".join(text for _, text in info)
        assert "mana ?" in parts

    def test_format_cwd_replaces_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mvgeos_cli.commands import repl as repl_mod

        monkeypatch.chdir(Path.home())
        assert repl_mod._format_cwd() == "~"

    def test_fit_footer_truncates_right_side(self) -> None:
        from mvgeos_cli.commands.repl import _fit_footer

        items = [
            ("bold", " ~/proj (main)"),
            ("dim", "  session abc12345"),
            ("", "  nvidia/nemotron-3-ultra-550b-a55b:free • medium"),
        ]
        fitted = _fit_footer(items, 40)
        plain = "".join(text for _, text in fitted)
        assert len(plain) == 40
        assert plain.endswith("…")

    def test_fit_footer_no_truncation_when_fits(self) -> None:
        from mvgeos_cli.commands.repl import _fit_footer

        items = [("bold", " ~/proj"), ("", "  nvidia/nemotron-3-ultra-550b-a55b:free")]
        fitted = _fit_footer(items, 80)
        assert fitted == items

    def test_git_branch_returns_none_outside_repo(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from mvgeos_cli.commands import repl as repl_mod

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GIT_DIR", raising=False)
        monkeypatch.delenv("GIT_WORK_TREE", raising=False)
        assert repl_mod._git_branch() is None

    def test_slash_completer(self) -> None:
        from prompt_toolkit.document import Document

        from mvgeos_cli.commands.repl import SlashCompleter

        completer = SlashCompleter()
        doc = Document("/hel", 4)
        completions = list(completer.get_completions(doc, None))
        assert any(c.text == "/help" for c in completions)

    def test_slash_completer_no_slash(self) -> None:
        from prompt_toolkit.document import Document

        from mvgeos_cli.commands.repl import SlashCompleter

        completer = SlashCompleter()
        doc = Document("hello", 5)
        completions = list(completer.get_completions(doc, None))
        assert completions == []

    def test_display_response(self) -> None:
        from mvgeos_agent.types import MvgeResponse, StopReason

        from mvgeos_cli.commands.repl import _display_response

        response = MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "Hello world"}],
            stop_reason=StopReason.STOP,
        )
        _display_response(response)

    def test_handle_command_steer(self) -> None:
        from unittest.mock import MagicMock

        from mvgeos_provider.model_registry import ModelRegistry

        from mvgeos_cli.commands.repl import _handle_command

        agent = MagicMock()
        registry = ModelRegistry()
        out_messages: list[str] = []

        _handle_command("/steer msg", agent, registry, out=out_messages.append)
        agent.steer.assert_called_once_with("msg")
        assert any("Steering queued" in m for m in out_messages)

    def test_handle_command_followup(self) -> None:
        from unittest.mock import MagicMock

        from mvgeos_provider.model_registry import ModelRegistry

        from mvgeos_cli.commands.repl import _handle_command

        agent = MagicMock()
        registry = ModelRegistry()
        out_messages: list[str] = []

        _handle_command("/followup msg", agent, registry, out=out_messages.append)
        agent.follow_up.assert_called_once_with("msg")
        assert any("Follow-up queued" in m for m in out_messages)

    def test_handle_command_mode_toggle(self) -> None:
        from unittest.mock import MagicMock

        from mvgeos_agent.types import QueueMode
        from mvgeos_provider.model_registry import ModelRegistry

        from mvgeos_cli.commands.repl import _handle_command

        agent = MagicMock()
        agent.queue_mode = QueueMode.ONE_AT_A_TIME
        registry = ModelRegistry()
        out_messages: list[str] = []

        _handle_command("/mode", agent, registry, out=out_messages.append)
        assert agent.queue_mode == QueueMode.ALL
        assert any("Queue mode: all" in m for m in out_messages)

        _handle_command("/m", agent, registry, out=out_messages.append)
        assert agent.queue_mode == QueueMode.ONE_AT_A_TIME
        assert any("Queue mode: one-at-a-time" in m for m in out_messages)


class TestStreamFilter:
    def test_channel_tag_stripped(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("Let me list <channel|list>\n") == "Let me list\n"

    def test_channel_tag_alone(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("<channel|list>\n") == ""

    def test_channel_tag_partial_across_chunks(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("see <channel|") == "see "
        assert f.feed("list>\n") == ""
        assert f.feed("Done\n") == "Done\n"

    def test_thinking_heading_preserved_as_markdown(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("# thinking\n") == "# thinking\n"
        assert f.feed("I'll check the dir.\n") == "I'll check the dir.\n"
        assert f.feed("<channel|list>\n") == ""
        assert f.feed("Here is the answer\n") == "Here is the answer\n"

    def test_standalone_thought_preserved_as_text(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("thought\n") == "thought\n"
        assert f.feed("<channel|>\n") == ""
        assert f.feed("Result text\n") == "Result text\n"

    def test_reasoning_channel_suppresses_block(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("secret\n") == ""
        assert f.feed("# Summary\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("public\n") == "public\n"

    def test_normal_markdown_preserved(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("# Title\n") == "# Title\n"
        assert f.feed("body\n") == "body\n"

    def test_empty_lines_preserved(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("a\n\nb\n") == "a\n\nb\n"

    def test_flush_pending(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("Hello") == "Hello"
        assert f.flush() == ""

    def test_flush_reasoning_discards(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("<channel|reasoning>") == ""
        assert f.flush() == ""

    def test_flush_clean_line(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        assert f.feed("see <channel|list>") == "see "
        assert f.flush() == ""

    def test_reset_clears_state(self) -> None:
        from mvgeos_cli.commands.repl import _StreamFilter

        f = _StreamFilter()
        f.feed("<channel|reasoning>\n")
        f.reset()
        assert f.feed("clean\n") == "clean\n"


def _message_event(text: str) -> MvgeEvent:
    return MvgeEvent(type=MvgeEventType.MESSAGE_UPDATE, data={"text": text})


def _tool_start_event(name: str, args: dict[str, Any]) -> MvgeEvent:
    return MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={"spellCastId": "call-1", "spellName": name, "arguments": args},
    )


def _tool_end_event(result: Any = None, error: str | None = None) -> MvgeEvent:
    data: dict[str, Any] = {"spellCastId": "call-1", "spellName": "bash"}
    if error is not None:
        data["error"] = error
    else:
        data["result"] = result
    return MvgeEvent(type=MvgeEventType.SPELL_CASTING_END, data=data)


class TestStreamRenderer:
    def test_leaked_markers_not_displayed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        for text in [
            "<channel|reasoning>\n",
            "Suppressed thinking\n",
            "<channel|>\n",
            "Result text\n",
        ]:
            renderer.on_message_update(_message_event(text))
        renderer.finish()
        captured = capsys.readouterr()
        assert "Suppressed thinking" not in captured.out
        assert "<channel|>" not in captured.out
        assert "Result text" in captured.out

    def test_turn_start_resets_contemplation_buffer(self) -> None:
        from mvgeos_agent.types import MvgeEvent, MvgeEventType

        from mvgeos_cli.commands.repl import StreamRenderer
        from mvgeos_cli.commands.tui import TuiSink

        sink = TuiSink()
        renderer = StreamRenderer(sink)

        # Turn 1
        renderer.on_turn_start(MvgeEvent(type=MvgeEventType.TURN_START, data={}))
        renderer.on_message_update(
            MvgeEvent(
                type=MvgeEventType.MESSAGE_UPDATE,
                data={"text": "Thinking 1", "kind": "contemplation"},
            )
        )
        renderer.on_message_update(
            MvgeEvent(
                type=MvgeEventType.MESSAGE_UPDATE,
                data={"text": "Response 1", "kind": "text"},
            )
        )
        renderer.on_turn_end(MvgeEvent(type=MvgeEventType.TURN_END, data={}))

        # Turn 2 (steer/followup)
        renderer.on_turn_start(MvgeEvent(type=MvgeEventType.TURN_START, data={}))
        renderer.on_message_update(
            MvgeEvent(
                type=MvgeEventType.MESSAGE_UPDATE,
                data={"text": "Thinking 2", "kind": "contemplation"},
            )
        )
        renderer.on_message_update(
            MvgeEvent(
                type=MvgeEventType.MESSAGE_UPDATE,
                data={"text": "Response 2", "kind": "text"},
            )
        )
        renderer.on_turn_end(MvgeEvent(type=MvgeEventType.TURN_END, data={}))

        md_entries = [e.md for e in sink._entries if e.kind == "md"]
        assert len(md_entries) == 2
        assert "> *Thinking: Thinking 1*" in md_entries[0]
        assert "Response 1" in md_entries[0]

        assert "> *Thinking: Thinking 2*" in md_entries[1]
        assert "Thinking 1" not in md_entries[1]
        assert "Response 2" in md_entries[1]

    def test_tool_cycle_shows_call_and_response(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "echo test"}))
        renderer.on_tool_end(_tool_end_event(result="test"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "[bash]  $ echo test" in captured.out
        assert "  test" in captured.out

    def test_tool_call_shows_duration(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "echo test"}))
        renderer.on_tool_end(_tool_end_event(result="test"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "[bash]" in captured.out
        assert "Took 0." in captured.out

    def test_multi_line_response_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(
            _tool_start_event("bash", {"command": "printf a; printf b"})
        )
        renderer.on_tool_end(_tool_end_event(result="line 1\nline 2\nline 3"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "  line 1" in captured.out
        assert "  line 2" in captured.out
        assert "  line 3" in captured.out

    def test_response_truncated_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        result = "\n".join(f"line {i}" for i in range(30))
        renderer.on_tool_start(_tool_start_event("bash", {"command": "seq 30"}))
        renderer.on_tool_end(_tool_end_event(result=result))
        renderer.finish()
        captured = capsys.readouterr()
        assert "line 0" in captured.out
        assert "line 29" not in captured.out
        assert "truncated: 10 more lines" in captured.out

    def test_response_long_line_capped(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        long = "x" * 500
        renderer.on_tool_start(_tool_start_event("bash", {"command": "echo x"}))
        renderer.on_tool_end(_tool_end_event(result=long))
        renderer.finish()
        captured = capsys.readouterr()
        assert "..." in captured.out
        assert "long lines capped" in captured.out
        assert "x" * 500 not in captured.out

    def test_response_empty_shows_no_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "true"}))
        renderer.on_tool_end(_tool_end_event(result=""))
        renderer.finish()
        captured = capsys.readouterr()
        assert "(no output)" in captured.out

    def test_tool_error_rendered(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "false"}))
        renderer.on_tool_end(_tool_end_event(error="exit code 1"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "[error] exit code 1" in captured.out

    def test_orphan_tool_end_renders_call_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_end(_tool_end_event(error="spell_not_found"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "[bash]" in captured.out
        assert "[error] spell_not_found" in captured.out

    def test_no_spells_footer(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "echo test"}))
        renderer.on_tool_end(_tool_end_event(result="test"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "Spells:" not in captured.out

    def test_interrupted_tool_marked(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "sleep 5"}))
        renderer.finish()
        captured = capsys.readouterr()
        assert "(interrupted)" in captured.out

    def test_narration_then_tool_starts_on_fresh_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_message_update(_message_event("Let me check"))
        renderer.on_tool_start(_tool_start_event("list", {}))
        renderer.on_tool_end(_tool_end_event(result="a.txt\nb.txt"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "Let me check\n  [list]" in captured.out
        assert "  a.txt" in captured.out

    def test_colors_emitted_when_terminal_forced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import io

        from rich.console import Console

        from mvgeos_cli.commands import repl as repl_mod

        buf = io.StringIO()
        monkeypatch.setattr(
            repl_mod,
            "console",
            Console(file=buf, force_terminal=True, color_system="truecolor"),
        )
        renderer = repl_mod.StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "echo test"}))
        renderer.on_tool_end(_tool_end_event(result="test"))
        renderer.on_tool_start(_tool_start_event("list", {"cwd": "."}))
        renderer.on_tool_end(_tool_end_event(result="a.txt"))
        renderer.finish()
        out = buf.getvalue()
        assert "\x1b[1;48;2;40;40;50m[bash]\x1b[0m" in out
        assert '\x1b[33;48;2;40;40;50m  {"cwd":"."}' in out
        assert "\x1b[48;2;40;50;40m  test" in out
        assert "\x1b[2;48;2;40;50;40m  Took" in out

    def test_error_colored_red_when_terminal_forced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import io

        from rich.console import Console

        from mvgeos_cli.commands import repl as repl_mod

        buf = io.StringIO()
        monkeypatch.setattr(
            repl_mod,
            "console",
            Console(file=buf, force_terminal=True, color_system="truecolor"),
        )
        renderer = repl_mod.StreamRenderer()
        renderer.on_tool_start(_tool_start_event("bash", {"command": "false"}))
        renderer.on_tool_end(_tool_end_event(error="exit code 1"))
        renderer.finish()
        out = buf.getvalue()
        assert "\x1b[1;31;48;2;60;40;40m  [error] exit code 1" in out

    def test_markdown_narration_rendered_when_terminal_forced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import io

        from rich.console import Console

        from mvgeos_cli.commands import repl as repl_mod

        buf = io.StringIO()
        monkeypatch.setattr(
            repl_mod,
            "console",
            Console(file=buf, force_terminal=True, color_system="truecolor"),
        )
        renderer = repl_mod.StreamRenderer()
        renderer.on_message_update(_message_event("Hello **world** with `code`\n"))
        renderer.finish()
        out = buf.getvalue()
        assert "\x1b[1mworld\x1b[0m" in out
        assert "code" in out

    def test_bash_title_shows_command_not_json(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_start(
            _tool_start_event("bash", {"command": "ls -la", "timeout": 5})
        )
        renderer.on_tool_end(_tool_end_event(result="total 0"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "[bash]  $ ls -la" in captured.out
        assert "(timeout 5s)" in captured.out

    def test_orphan_tool_end_has_no_duration(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mvgeos_cli.commands.repl import StreamRenderer

        renderer = StreamRenderer()
        renderer.on_tool_end(_tool_end_event(error="spell_not_found"))
        renderer.finish()
        captured = capsys.readouterr()
        assert "Took" not in captured.out

    def test_live_failure_falls_back_to_plain_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import io

        from rich.console import Console

        from mvgeos_cli.commands import repl as repl_mod

        buf = io.StringIO()
        monkeypatch.setattr(
            repl_mod,
            "console",
            Console(file=buf, force_terminal=True, color_system="truecolor"),
        )
        renderer = repl_mod.StreamRenderer()

        class Boom:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError("live unavailable")

        monkeypatch.setattr(repl_mod, "Live", Boom)
        renderer.on_message_update(_message_event("plain fallback text\n"))
        renderer.finish()
        out = buf.getvalue()
        assert "plain fallback text" in out
