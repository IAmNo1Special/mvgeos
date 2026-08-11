from __future__ import annotations

import asyncio
import re
from typing import Any
from unittest.mock import patch

import pytest
from mvgeos_agent.types import MvgeEvent, MvgeEventType
from rich.markup import render as render_markup

from mvgeos_cli.commands.repl import StreamRenderer, _handle_command
from mvgeos_cli.commands.tui import TranscriptControl, TuiSink


def _message_event(text: str) -> MvgeEvent:
    return MvgeEvent(type=MvgeEventType.MESSAGE_UPDATE, data={"text": text})


def _tool_start_event(name: str, args: dict[str, Any]) -> MvgeEvent:
    return MvgeEvent(
        type=MvgeEventType.SPELL_CASTING_START,
        data={"spellName": name, "arguments": args},
    )


def _tool_end_event(result: Any = None, error: str | None = None) -> MvgeEvent:
    data: dict[str, Any] = {}
    if result is not None:
        data["result"] = result
    if error is not None:
        data["error"] = error
    return MvgeEvent(type=MvgeEventType.SPELL_CASTING_END, data=data)


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestTuiSink:
    def test_write_accumulates_partial_lines(self) -> None:
        sink = TuiSink()
        sink.write("hello")
        assert sink.line_dirty is True
        sink.write(" world\n")
        assert sink.line_dirty is False
        assert sink._entries[0].text is not None
        assert sink._entries[0].text.plain == "hello world"

    def test_write_newline_adds_blank_separator(self) -> None:
        sink = TuiSink()
        sink.write("\n")
        assert sink._entries[0].text is not None
        assert sink._entries[0].text.plain == ""

    def test_narration_buffered_until_finalize(self) -> None:
        sink = TuiSink()
        sink.stream_narration("one", "one")
        assert sink._pending_md == "one"
        assert sink._entries == []
        sink.finalize_narration()
        assert sink._pending_md is None
        assert len(sink._entries) == 1
        assert sink._entries[0].kind == "md"
        assert sink._entries[0].md == "one"

    def test_finalize_narration_noop_without_pending(self) -> None:
        sink = TuiSink()
        sink.finalize_narration()
        assert sink._entries == []

    def test_renderer_events_build_transcript(self) -> None:
        sink = TuiSink()
        renderer = StreamRenderer(sink)
        renderer.on_message_update(_message_event("Let me **check**.\n"))
        renderer.on_tool_start(_tool_start_event("bash", {"command": "ls"}))
        renderer.on_tool_end(_tool_end_event(result="a.txt"))
        renderer.finish()
        kinds = [e.kind for e in sink._entries]
        assert "md" in kinds
        text_kinds = [e for e in sink._entries if e.kind == "text"]
        assert any(
            e.text is not None and e.text.plain.startswith("  [bash]")
            for e in text_kinds
        )
        assert any(e.text is not None and e.text.plain == "  a.txt" for e in text_kinds)
        assert any(e.text is not None and "Took" in e.text.plain for e in text_kinds)

    def test_render_to_ansi_pads_cards_and_bolds_markdown(self) -> None:
        sink = TuiSink()
        renderer = StreamRenderer(sink)
        renderer.on_message_update(_message_event("Hello **world**\n"))
        renderer.on_tool_start(_tool_start_event("bash", {"command": "ls"}))
        renderer.on_tool_end(_tool_end_event(result="a.txt"))
        renderer.finish()
        lines = sink.render_to_ansi(30)
        joined = "\n".join(lines)
        assert "\x1b[1mworld\x1b[0m" in joined
        assert "\x1b[1;48;2;40;40;50m[bash]\x1b[0m" in joined
        card_lines = [ln for ln in lines if "[bash]" in ln or "a.txt" in ln]
        assert card_lines
        for ln in card_lines:
            assert len(_strip_ansi(ln)) == 30

    def test_render_to_ansi_truncates_long_lines(self) -> None:
        sink = TuiSink()
        sink.write_card_line(__import__("rich").text.Text("x" * 50), "#282832")
        lines = sink.render_to_ansi(20)
        assert len(_strip_ansi(lines[0])) == 20
        assert _strip_ansi(lines[0]).endswith("…")

    def test_version_bumps_on_mutation(self) -> None:
        sink = TuiSink()
        v0 = sink.version
        sink.write("a\n")
        assert sink.version > v0

    def test_print_transcript(self, capsys: pytest.CaptureFixture[str]) -> None:
        sink = TuiSink()
        renderer = StreamRenderer(sink)
        renderer.on_message_update(_message_event("note **bold**\n"))
        renderer.on_tool_start(_tool_start_event("list", {"cwd": "."}))
        renderer.on_tool_end(_tool_end_event(result="b.txt"))
        renderer.finish()
        sink.print_transcript()
        out = capsys.readouterr().out
        assert "note" in out
        assert "[list]" in out
        assert "b.txt" in out


class TestTranscriptControl:
    def _render(self, sink: TuiSink) -> TranscriptControl:
        return TranscriptControl(sink)

    def test_follow_pins_to_end(self) -> None:
        sink = TuiSink()
        for i in range(10):
            sink.write(f"line {i}\n")
        ctrl = self._render(sink)
        top = ctrl._update_scroll(10, 4)
        assert ctrl.following is True
        assert top == 6

    def test_scroll_up_disables_follow(self) -> None:
        sink = TuiSink()
        for i in range(10):
            sink.write(f"line {i}\n")
        ctrl = self._render(sink)
        ctrl._update_scroll(10, 4)
        ctrl.scroll_up(3)
        assert ctrl.following is False
        assert ctrl.scroll_top == 3
        ctrl._update_scroll(10, 4)
        assert ctrl.scroll_top == 3

    def test_scroll_down_to_end_reenables_follow(self) -> None:
        sink = TuiSink()
        for i in range(10):
            sink.write(f"line {i}\n")
        ctrl = self._render(sink)
        ctrl._update_scroll(10, 4)
        ctrl.scroll_up(9)
        ctrl._update_scroll(10, 4)
        assert ctrl.following is False
        ctrl.scroll_to_bottom()
        assert ctrl.following is True

    def test_scroll_to_top(self) -> None:
        sink = TuiSink()
        for i in range(10):
            sink.write(f"line {i}\n")
        ctrl = self._render(sink)
        ctrl._update_scroll(10, 4)
        ctrl.scroll_to_top()
        assert ctrl.following is False
        assert ctrl.scroll_top == 0

    def test_create_content_shows_visible_window(self) -> None:
        sink = TuiSink()
        for i in range(10):
            sink.write(f"line {i}\n")
        ctrl = self._render(sink)
        content = ctrl.create_content(40, 3)
        assert content.line_count == 3
        visible = [
            _strip_ansi(tuple(frags) and "".join(t for _, t in frags))
            for frags in [content.get_line(i) for i in range(3)]
        ]
        assert "line 9" in "".join(visible)

    def test_content_caches_by_version_and_width(self) -> None:
        sink = TuiSink()
        sink.write("hello\n")
        ctrl = self._render(sink)
        a = ctrl._get_lines(20)
        b = ctrl._get_lines(20)
        assert a is b
        c = ctrl._get_lines(30)
        assert c is not a


class TestHandleCommandOut:
    def test_out_routes_output(self) -> None:
        from coding_mvge import CodingMvge

        from mvgeos_cli.commands.repl import ReplAction

        agent = CodingMvge(api_key="test-key")
        captured: list[str] = []
        action = _handle_command("/help", agent, object(), out=captured.append)
        assert action == ReplAction.CONTINUE
        assert any("/quit" in line for line in captured)


class FakeAgent:
    def __init__(self, session_id: str = "abcd1234efgh") -> None:
        self.session_id = session_id
        self._model_id = "nvidia/nemotron-3-ultra-550b-a55b:free"
        self._contemplation_level = "medium"
        self._initialized = False
        self.closed = False
        self.initialize_calls = 0
        self.run_calls: list[str] = []
        self.error: Exception | None = None

    def on(self, name: str, cb: Any) -> Any:
        return lambda: None

    async def run(self, text: str) -> None:
        self.run_calls.append(text)
        if self.error is not None:
            raise self.error

    async def close(self) -> None:
        self.closed = True

    async def initialize(self) -> None:
        self._initialized = True
        self.initialize_calls += 1

    async def switch_model(self, model: str) -> None:
        self._model_id = model


class FakeRegistry:
    def get(self, model_id: str) -> object | None:
        return object() if model_id else None

    def list_all(self) -> list[Any]:
        return []


class TestTuiApp:
    def _app(self, agent: FakeAgent, sink: TuiSink | None = None) -> Any:
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        from mvgeos_cli.commands.tui import TuiApp

        sink = sink or TuiSink()
        with create_pipe_input() as pin:
            return TuiApp(
                agent,
                sink,
                FakeRegistry(),
                StreamRenderer(sink),
                input=pin,
                output=DummyOutput(),
            )

    def test_app_constructs(self) -> None:
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        from mvgeos_cli.commands.tui import TuiApp

        sink = TuiSink()
        agent = FakeAgent()
        with create_pipe_input() as pin:
            app = TuiApp(
                agent,
                sink,
                FakeRegistry(),
                StreamRenderer(sink),
                input=pin,
                output=DummyOutput(),
            )
        assert app.application is not None
        with patch(
            "mvgeos_cli.commands.repl._fit_footer",
            side_effect=lambda items, width: items,
        ):
            footer = app._footer_text()
            assert any("nvidia" in text for _, text in footer)

    def test_footer_shows_working_while_busy(self) -> None:
        app = self._app(FakeAgent())
        assert not any("(working)" in t for _, t in app._footer_text())
        app._busy = True
        assert any("(working)" in t for _, t in app._footer_text())

    def test_out_writes_card_line(self) -> None:
        sink = TuiSink()
        app = self._app(FakeAgent(), sink)
        app._out("[red]boom[/red]")
        assert len(sink._entries) == 1
        entry = sink._entries[0]
        assert entry.kind == "text"
        assert "boom" in (entry.text or "").plain

    def test_accept_rejects_empty(self) -> None:
        app = self._app(FakeAgent())
        app._buffer.text = "   "
        assert app._on_accept(app._buffer) is False
        assert app._task is None

    def test_accept_busy_ignores_input(self) -> None:
        sink = TuiSink()
        app = self._app(FakeAgent(), sink)
        app._busy = True
        app._buffer.text = "hello"
        assert app._on_accept(app._buffer) is True
        assert app._task is None
        assert any("Busy" in (e.text or "").plain for e in sink._entries)

    @pytest.mark.asyncio
    async def test_accept_runs_turn(self) -> None:
        agent = FakeAgent()
        app = self._app(agent)
        app._buffer.text = "hi"
        assert app._on_accept(app._buffer) is True
        assert app._task is not None
        await app._task
        assert agent.run_calls == ["hi"]
        assert app._busy is False
        assert app._task is None

    @pytest.mark.asyncio
    async def test_run_turn_error_renders_notice(self) -> None:
        agent = FakeAgent()
        agent.error = RuntimeError("nope")
        sink = TuiSink()
        app = self._app(agent, sink)
        app._buffer.text = "hi"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        plain = "\n".join((e.text or "").plain for e in sink._entries)
        assert "Error: nope" in plain

    @pytest.mark.asyncio
    async def test_run_turn_cancelled_renders_notice(self) -> None:
        class CancelAgent(FakeAgent):
            async def run(self, text: str) -> None:
                raise asyncio.CancelledError

        sink = TuiSink()
        app = self._app(CancelAgent(), sink)
        app._buffer.text = "hi"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        plain = "\n".join((e.text or "").plain for e in sink._entries)
        assert "Interrupted" in plain

    @pytest.mark.asyncio
    async def test_slash_new_session(self) -> None:
        agent = FakeAgent()
        app = self._app(agent)
        app._buffer.text = "/new"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        assert agent.closed is True
        assert agent.initialize_calls == 1
        plain = "\n".join((e.text or "").plain for e in app.sink._entries)
        assert "New session" in plain

    @pytest.mark.asyncio
    async def test_slash_model_switch(self) -> None:
        agent = FakeAgent()
        app = self._app(agent)
        app._buffer.text = "/model nvidia/nemotron-3-ultra-550b-a55b:free"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        assert agent._model_id == "nvidia/nemotron-3-ultra-550b-a55b:free"
        plain = "\n".join((e.text or "").plain for e in app.sink._entries)
        assert "Model switched" in plain

    @pytest.mark.asyncio
    async def test_slash_unknown_model_renders_error(self) -> None:
        class EmptyRegistry(FakeRegistry):
            def get(self, model_id: str) -> object | None:
                return None

        agent = FakeAgent()
        app = self._app(agent)
        app.registry = EmptyRegistry()
        app._buffer.text = "/model bogus"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        assert agent._model_id == "nvidia/nemotron-3-ultra-550b-a55b:free"
        plain = "\n".join((e.text or "").plain for e in app.sink._entries)
        assert "Unknown model" in plain

    @pytest.mark.asyncio
    async def test_slash_switch_model_error_renders(self) -> None:
        class FailSwitch(FakeAgent):
            async def switch_model(self, model: str) -> None:
                raise ValueError("bad model")

        agent = FailSwitch()
        app = self._app(agent)
        app._buffer.text = "/model nvidia/nemotron-3-ultra-550b-a55b:free"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        plain = "\n".join((e.text or "").plain for e in app.sink._entries)
        assert "bad model" in plain

    @pytest.mark.asyncio
    async def test_slash_exit(self) -> None:
        app = self._app(FakeAgent())
        exits: list[Any] = []
        app.application.exit = lambda *a, **k: exits.append(1)  # type: ignore[method-assign]
        app._buffer.text = "/quit"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        assert exits == [1]

    @pytest.mark.asyncio
    async def test_slash_new_session_initialize_error(self) -> None:
        class FailInit(FakeAgent):
            async def initialize(self) -> None:
                raise ValueError("no api key")

        agent = FailInit()
        app = self._app(agent)
        app._buffer.text = "/new"
        app._on_accept(app._buffer)
        assert app._task is not None
        await app._task
        plain = "\n".join((e.text or "").plain for e in app.sink._entries)
        assert "no api key" in plain

    def test_print_transcript_truncates_bg_card(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from rich.text import Text

        sink = TuiSink()
        sink.write_card_line(Text("x" * 200), "#282832")
        sink.print_transcript()
        out = _strip_ansi(capsys.readouterr().out).strip()
        assert len(out) < 200
        assert out.endswith("…")

    def test_redraw_callback_invoked_on_write(self) -> None:
        sink = TuiSink()
        calls: list[int] = []
        sink.set_redraw_cb(lambda: calls.append(1))
        sink.write("a\n")
        sink.write_card_line(render_markup("x"), None)
        sink.stream_narration("m", "m")
        sink.finalize_narration()
        assert len(calls) >= 3

    def test_write_merges_partials(self) -> None:
        sink = TuiSink()
        sink.write("pre")
        sink.write("suffix\n")
        assert any(
            e.text is not None and e.text.plain == "presuffix" for e in sink._entries
        )

    def test_card_line_resets_partial_state(self) -> None:
        sink = TuiSink()
        sink.write("pre")
        sink.write_card_line(render_markup("card"), None)
        sink.write("suffix\n")
        plains = [(e.text or "").plain for e in sink._entries]
        assert plains == ["pre", "card", "suffix"]

    def test_render_to_ansi_splits_newlines_in_card_line(self) -> None:
        sink = TuiSink()
        sink.write_card_line(render_markup("Rate limited\nby the provider."), None)
        lines = sink.render_to_ansi(80)
        assert "Rate limited" in _strip_ansi(lines[0])
        assert "by the provider." in _strip_ansi(lines[1])
        for line in lines:
            assert "\n" not in _strip_ansi(line)

    def test_write_after_md_entry_starts_new_text(self) -> None:
        sink = TuiSink()
        sink.write("partial")
        sink.stream_narration("**md**", "**md**")
        sink.finalize_narration()
        sink.write("tail\n")
        kinds = [e.kind for e in sink._entries]
        assert kinds == ["text", "md", "text"]

    def test_scroll_down_clamp_reenables_follow(self) -> None:
        sink = TuiSink()
        for i in range(10):
            sink.write(f"line {i}\n")
        ctrl = TranscriptControl(sink)
        ctrl._update_scroll(10, 4)
        ctrl.scroll_up(9)
        ctrl._update_scroll(10, 4)
        assert ctrl.following is False
        assert ctrl.scroll_top == 0
        ctrl.scroll_down(6)
        assert ctrl.scroll_top == 6
        assert ctrl.following is False
        ctrl._update_scroll(10, 4)
        assert ctrl.following is True
