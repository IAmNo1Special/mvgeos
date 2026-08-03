from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Generator
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from coding_mvge import CodingMvge
from mvgeos_agent.errors import AuthenticationError, RateLimitError
from mvgeos_agent.types import MvgeEvent, MvgeResponse
from mvgeos_provider.model_registry import ModelRegistry
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from mvgeos_cli import DEFAULT_MODEL

logger = logging.getLogger(__name__)

console = Console()


class ReplAction(StrEnum):
    CONTINUE = "continue"
    EXIT = "exit"
    NEW_SESSION = "new_session"
    SWITCH_MODEL = "switch_model"


SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show this help message",
    "/quit": "Exit the REPL",
    "/exit": "Exit the REPL",
    "/model": "Switch model: /model <model-id>",
    "/new": "Start a new session",
    "/session": "Show current session info",
    "/resume": "Resume a previous session: /resume <path>",
    "/spells": "List or set enabled spells: /spells [comma-separated]",
    "/refresh-models": "Refresh model catalog from OpenRouter API",
}

REPL_STYLE = Style.from_dict(
    {
        "prompt": "bold green",
        "toolbar": "bg:#333333 #aaaaaa",
        "slash": "bold cyan",
    }
)


class SlashCompleter(Completer):
    def get_completions(
        self, document: Document, complete_event: Any
    ) -> Generator[Completion]:
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd, desc in SLASH_COMMANDS.items():
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc,
                    )


def _make_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-c")
    def _(event: Any) -> None:
        event.app.exit(exception=KeyboardInterrupt)

    @bindings.add("c-d")
    def _(event: Any) -> None:
        text = event.app.current_buffer.text
        if not text.strip():
            event.app.exit(exception=EOFError)

    return bindings


def _get_history_path() -> Path:
    path = Path(os.path.expanduser("~/.agents/.mvgeos/history"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _format_cwd() -> str:
    home = Path.home()
    try:
        rel = Path.cwd().relative_to(home)
    except ValueError:
        return str(Path.cwd())
    if str(rel) == ".":
        return "~"
    return f"~/{rel.as_posix()}"


def _git_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _mana_context(agent: CodingMvge) -> tuple[str, str]:
    state = getattr(agent, "_state", None)
    if state is None or not getattr(state, "mana_budget", None):
        return "", "mana ?"
    used = getattr(state, "mana_used", 0) or 0
    budget = state.mana_budget
    pct = (used / budget) * 100
    style = ""
    if pct > 90:
        style = "red"
    elif pct > 70:
        style = "yellow"
    return style, f"mana {pct:.0f}%/{budget}"


def _fit_footer(items: list[tuple[str, str]], width: int) -> list[tuple[str, str]]:
    total = sum(len(text) for _, text in items)
    if total <= width:
        return items
    room = width - (total - len(items[-1][1]))
    style, text = items[-1]
    if room < 1:
        return items[:-1]
    return items[:-1] + [(style, text[: room - 1] + "…")]


def _format_session_info(
    agent: CodingMvge, branch: str | None = None
) -> list[tuple[str, str]]:
    cwd = _format_cwd()
    if branch:
        cwd = f"{cwd} ({branch})"
    items: list[tuple[str, str]] = [("bold", f" {cwd}")]
    sid = agent.session_id
    if sid:
        items.append(("dim", f"  session {sid[:8]}"))
    mana_style, mana_text = _mana_context(agent)
    items.append((mana_style, f"  {mana_text}"))
    right = agent._model_id
    thinking = getattr(agent, "_contemplation_level", None)
    if thinking:
        right = f"{right} • {thinking}"
    items.append(("", f"  {right}"))
    return _fit_footer(items, console.width)


def _render_exception(exc: Exception) -> str | None:
    """Return friendly rich markup for known errors, else None."""
    if isinstance(exc, RateLimitError):
        hint = ""
        if exc.retry_after is not None:
            hint = f" Try again in {exc.retry_after:.0f}s."
        return f"[yellow]Rate limited by the provider.{hint}[/yellow]"
    if isinstance(exc, AuthenticationError):
        return (
            "[red]Authentication failed (401). "
            "Check your OPENROUTER_API_KEY or --api-key.[/red]"
        )
    return None


def _handle_command(
    command: str,
    agent: CodingMvge,
    registry: ModelRegistry,
    out: Callable[[str], None] = console.print,
) -> ReplAction:
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit"):
        return ReplAction.EXIT

    if cmd == "/help":
        out("[bold]Available commands:[/bold]")
        for name, desc in SLASH_COMMANDS.items():
            out(f"  [cyan]{name:<15}[/cyan] {desc}")
        return ReplAction.CONTINUE

    if cmd == "/session":
        sid = agent.session_id or "none"
        out(f"[dim]Session ID: {sid}[/dim]")
        out(f"[dim]Model: {agent._model_id}[/dim]")
        out(f"[dim]Spells: {', '.join(agent.enabled_spells)}[/dim]")
        out(f"[dim]Providers: {', '.join(agent.registered_providers) or 'none'}[/dim]")
        return ReplAction.CONTINUE

    if cmd == "/model":
        if not args:
            out(f"[bold]Current model:[/bold] {agent._model_id}")
            out("[bold]Available models:[/bold]")
            for m in registry.list_all():
                out(f"  {m.id}")
            out("[dim]Try /refresh-models to fetch the latest catalog[/dim]")
            return ReplAction.CONTINUE
        candidate = args.strip()
        if registry.get(candidate) is None:
            out(f"[red]Unknown model: {candidate}[/red]")
            out("[dim]Try /refresh-models to fetch the latest catalog[/dim]")
            return ReplAction.CONTINUE
        agent._model_id = candidate
        return ReplAction.SWITCH_MODEL

    if cmd == "/refresh-models":
        out("[yellow]Fetching latest models from OpenRouter...[/yellow]")
        return ReplAction.CONTINUE  # handled in REPL loop

    if cmd == "/spells":
        if args:
            new_spells = [s.strip() for s in args.split(",") if s.strip()]
            agent._spell_names = new_spells
            out(f"[green]Spells set to: {', '.join(new_spells)}[/green]")
        else:
            out(f"[dim]Spells: {', '.join(agent.enabled_spells)}[/dim]")
        return ReplAction.CONTINUE

    if cmd == "/new":
        return ReplAction.NEW_SESSION

    if cmd == "/resume":
        if args:
            agent._session_resume = args.strip()
            out(f"[green]Will resume: {agent._session_resume}[/green]")
            return ReplAction.NEW_SESSION
        out("[red]Usage: /resume <path-to-session.jsonl>[/red]")
        return ReplAction.CONTINUE

    out(f"[red]Unknown command: {cmd}[/red]")
    out("[dim]Type /help for available commands[/dim]")
    return ReplAction.CONTINUE


def _display_response(result: Any) -> None:
    if isinstance(result, MvgeResponse):
        for item in result.content:
            if item.get("type") == "text":
                md = Markdown(str(item.get("text", "")))
                console.print(md)
        if result.stop_reason:
            console.print(f"[dim]Stop reason: {result.stop_reason.value}[/dim]")


async def _read_initial_prompt(
    session: PromptSession[Any],
    toolbar: Any,
) -> str | None:
    try:
        result: str = await session.prompt_async(
            "> ",
            bottom_toolbar=toolbar,
            multiline=False,
        )
        return result
    except KeyboardInterrupt, EOFError:
        return None


class _StreamFilter:
    """Strips pi-style channel markers and thinking blocks from streamed text.

    Some models emit reasoning artifacts in the content channel, e.g.
    ``# thinking`` headings or ``<channel|name>`` markers. These are hidden
    from the REPL display while normal markdown output is preserved.
    """

    _THINKING_HEADING = re.compile(r"^#\s*(?:thinking|thought|reasoning)\b", re.I)
    _STANDALONE_THINK = re.compile(
        r"^\s*(?:thinking|thought|reasoning)s?[:]?\s*$", re.I
    )
    _OTHER_HEADING = re.compile(r"^\s*#\s+\S+")
    _CHANNEL_TAG = re.compile(r"<\s*channel\s*\|[^>]*>", re.I)

    def __init__(self) -> None:
        self._pending = ""
        self._in_thinking = False

    def feed(self, text: str) -> str:
        self._pending += text
        out: list[str] = []
        while True:
            idx = self._pending.find("\n")
            if idx == -1:
                break
            line = self._pending[:idx]
            self._pending = self._pending[idx + 1 :]
            filtered = self._process_line(line)
            if filtered is None:
                continue
            out.append(filtered)
            out.append("\n")
        return "".join(out)

    def flush(self) -> str:
        leftover = self._pending
        self._pending = ""
        if not leftover:
            return ""
        filtered = self._process_line(leftover)
        if filtered is None:
            return ""
        return filtered

    def reset(self) -> None:
        self._pending = ""
        self._in_thinking = False

    def _process_line(self, line: str) -> str | None:
        """Return cleaned line content, or None to suppress the line."""
        stripped = line.strip()
        if self._in_thinking:
            if self._THINKING_HEADING.match(stripped):
                return None
            if self._CHANNEL_TAG.search(line):
                self._in_thinking = False
                return self._clean_line(line)
            if self._OTHER_HEADING.match(stripped):
                self._in_thinking = False
                return self._clean_line(line)
            return None
        if self._THINKING_HEADING.match(stripped) or self._STANDALONE_THINK.match(
            stripped
        ):
            self._in_thinking = True
            return None
        return self._clean_line(line)

    @staticmethod
    def _clean_line(line: str) -> str | None:
        if not line.strip():
            return ""
        cleaned = _StreamFilter._CHANNEL_TAG.sub("", line).rstrip()
        if not cleaned:
            return None
        return cleaned


_MAX_RESPONSE_LINES = 20
_MAX_LINE_CHARS = 200

_CARD_BG_PENDING = "#282832"
_CARD_BG_SUCCESS = "#283228"
_CARD_BG_ERROR = "#3c2828"


def _build_card(text: str, bg: str, extra: str = "") -> Text:
    style = f"on {bg}" + (f" {extra}" if extra else "")
    return Text(text, style=style)


def _build_card_title(name: str, args: Any, bg: str) -> Text:
    title = Text("  ", style=f"on {bg}")
    title.append(f"[{name}]", style=f"bold on {bg}")
    if name == "bash":
        cmd = (args or {}).get("command", "") if isinstance(args, dict) else ""
        title.append(f"  $ {cmd}", style=f"bold on {bg}")
        if isinstance(args, dict) and args.get("timeout"):
            title.append(f" (timeout {args['timeout']}s)", style=f"on {bg}")
    elif args:
        title.append(
            f"  {json.dumps(args, separators=(',', ':'))}",
            style=f"yellow on {bg}",
        )
    return title


class Sink(Protocol):
    """Presentation target for streamed agent output."""

    @property
    def line_dirty(self) -> bool: ...

    def write(self, text: str) -> None: ...

    def write_card_line(self, line: Text, bg: str | None = None) -> None: ...

    def stream_narration(self, chunk: str, full: str) -> None: ...

    def finalize_narration(self) -> None: ...


class ConsoleSink:
    """Terminal-scrollback sink: cards padded to width, narration via Live."""

    def __init__(self) -> None:
        self._line_dirty = False
        self._live: Live | None = None
        self._live_broken = False

    @property
    def line_dirty(self) -> bool:
        return self._line_dirty

    @property
    def _live_enabled(self) -> bool:
        return console.is_terminal and not self._live_broken

    def write(self, text: str) -> None:
        console.print(Text(text), end="", soft_wrap=True, highlight=False)
        self._line_dirty = not text.endswith("\n")

    def write_card_line(self, line: Text, bg: str | None = None) -> None:
        width = console.width
        pad = width - len(line)
        if pad > 0 and bg is not None:
            line = line.copy()
            style = line.style if line.style else f"on {bg}"
            line.append(" " * pad, style=style)
        console.print(line, end="\n", soft_wrap=True, highlight=False)
        self._line_dirty = False

    def stream_narration(self, chunk: str, full: str) -> None:
        if not self._live_enabled:
            self.write(chunk)
            return
        try:
            if self._live is None:
                self._live = Live(
                    Markdown(full),
                    console=console,
                    refresh_per_second=6,
                    transient=False,
                    vertical_overflow="ellipsis",
                )
                self._live.start()
            self._live.update(Markdown(full))
        except Exception:
            self._live_broken = True
            if self._live is not None:
                with suppress(Exception):
                    self._live.stop()
                self._live = None
            self.write(chunk)

    def finalize_narration(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None
                self._line_dirty = False


class StreamRenderer:
    def __init__(self, sink: Sink | None = None) -> None:
        self._sink = sink or ConsoleSink()
        self._text_parts: list[str] = []
        self._markdown_buffer = ""
        self._started = False
        self._filter = _StreamFilter()
        self._tool_line_open = False
        self._tool_start_time: float | None = None
        self._narration_finalized = False

    def _ensure_started(self) -> None:
        if not self._started:
            self._sink.write("\n")
            self._started = True

    def _write_card_line(self, text: str, bg: str, extra: str = "") -> None:
        self._sink.write_card_line(_build_card(text, bg, extra), bg)

    def _write_card_title(self, name: str, args: Any, bg: str) -> None:
        self._sink.write_card_line(_build_card_title(name, args, bg), bg)

    def _write_tool_call_line(self, name: str, args: Any) -> None:
        self._ensure_started()
        if self._sink.line_dirty:
            self._sink.write("\n")
        self._write_card_title(name, args, _CARD_BG_PENDING)
        self._tool_line_open = True
        self._tool_start_time = time.monotonic()

    def _write_response_block(self, text: str, bg: str) -> None:
        lines = text.splitlines()
        more = 0
        if len(lines) > _MAX_RESPONSE_LINES:
            more = len(lines) - _MAX_RESPONSE_LINES
            lines = lines[:_MAX_RESPONSE_LINES]
        if not lines:
            self._write_card_line("  (no output)", bg, extra="dim")
            return
        truncated_chars = False
        for i, line in enumerate(lines):
            if len(line) > _MAX_LINE_CHARS:
                lines[i] = line[:_MAX_LINE_CHARS] + "..."
                truncated_chars = True
        for line in lines:
            self._write_card_line(f"  {line}", bg)
        if more or truncated_chars:
            detail = []
            if more:
                detail.append(f"{more} more lines")
            if truncated_chars:
                detail.append("long lines capped")
            self._write_card_line(
                f"  ... (truncated: {', '.join(detail)})", bg, extra="dim"
            )

    @staticmethod
    def _result_to_text(result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    def on_message_update(self, event: MvgeEvent) -> None:
        text = str(event.data.get("text", ""))
        if not text:
            return
        clean = self._filter.feed(text)
        if not clean:
            return
        self._markdown_buffer += clean
        self._text_parts.append(clean)
        self._ensure_started()
        self._sink.stream_narration(clean, self._markdown_buffer)
        self._narration_finalized = False

    def on_tool_start(self, event: MvgeEvent) -> None:
        pending = self._filter.flush()
        if pending:
            self._markdown_buffer += pending
            self._ensure_started()
            self._sink.stream_narration(pending, self._markdown_buffer)
        self._sink.finalize_narration()
        self._narration_finalized = True
        name = str(event.data.get("spellName", "?"))
        args = event.data.get("arguments", {})
        self._write_tool_call_line(name, args)

    def on_tool_end(self, event: MvgeEvent) -> None:
        had_start = self._tool_start_time is not None
        if not self._tool_line_open and event.data.get("spellName"):
            self._write_tool_call_line(
                str(event.data["spellName"]), event.data.get("arguments", {})
            )
        elapsed = 0.0
        if self._tool_start_time is not None:
            elapsed = time.monotonic() - self._tool_start_time
        self._tool_line_open = False
        self._tool_start_time = None
        bg = _CARD_BG_ERROR if "error" in event.data else _CARD_BG_SUCCESS
        if "error" in event.data:
            msg = event.data.get("message") or event.data.get("error") or "tool failed"
            self._write_card_line(f"  [error] {msg}", bg, extra="bold red")
        elif "result" in event.data:
            self._write_response_block(self._result_to_text(event.data["result"]), bg)
        if had_start:
            self._write_card_line(f"  Took {elapsed:.1f}s", bg, extra="dim")

    def finish(self, *, error: bool = False) -> None:
        if self._tool_line_open:
            self._write_card_line("  (interrupted)", _CARD_BG_PENDING, extra="dim")
            self._tool_line_open = False
            self._tool_start_time = None
        if not error:
            pending = self._filter.flush()
            if pending:
                self._markdown_buffer += pending
                self._ensure_started()
                self._sink.stream_narration(pending, self._markdown_buffer)
            if not self._narration_finalized:
                self._sink.finalize_narration()
                self._narration_finalized = True
        if self._started:
            self._sink.write("\n")
        self._started = False

    def reset(self) -> None:
        if not self._narration_finalized:
            self._sink.finalize_narration()
        self._markdown_buffer = ""
        self._text_parts.clear()
        self._started = False
        self._filter.reset()
        self._tool_line_open = False
        self._tool_start_time = None
        self._narration_finalized = False


def _validate_api_key(api_key: str) -> None:
    """Validate OpenRouter API key format. Raises ValueError if invalid."""
    if not api_key or not api_key.startswith("sk-or-"):
        raise ValueError(
            "Invalid OpenRouter API key. It must start with 'sk-or-'. "
            "Get a key at https://openrouter.ai/keys"
        )


async def _create_agent(
    model: str,
    api_key: str,
    spells: str,
    extension_dir: str | None,
    session_dir: str | None,
    resume: str | None,
    provider: str | None,
    temperature: float,
    max_tokens: int,
    mana_budget: int,
    contemplation: str,
) -> CodingMvge:
    _validate_api_key(api_key)
    spells_list = [s.strip() for s in spells.split(",") if s.strip()]
    agent = CodingMvge(
        api_key=api_key,
        model=model,
        spells=spells_list,
        extension_dir=extension_dir,
        session_dir=Path(session_dir) if session_dir else None,
        session_resume=resume,
        provider_name=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        mana_budget=mana_budget,
        contemplation_level=contemplation,
    )
    await agent.initialize()
    return agent


async def run_repl(
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    spells: str = "bash,read,write,edit,find,list,grep",
    extension_dir: str | None = None,
    resume: str | None = None,
    provider: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    mana_budget: int = 10000,
    contemplation: str = "medium",
    session_dir: str | None = None,
) -> None:
    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key is None:
        console.print(
            "[red]API key required. Set OPENROUTER_API_KEY or pass --api-key[/red]"
        )
        return

    try:
        agent = await _create_agent(
            model=model,
            api_key=api_key,
            spells=spells,
            extension_dir=extension_dir,
            session_dir=session_dir,
            resume=resume,
            provider=provider,
            temperature=temperature,
            max_tokens=max_tokens,
            mana_budget=mana_budget,
            contemplation=contemplation,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    registry = ModelRegistry()
    registry.load_cache()

    console.print("[green]MvgeOS REPL[/green]")
    console.print(f"[dim]Model: {model}[/dim]")
    if agent.session_id:
        console.print(f"[dim]Session: {agent.session_id}[/dim]")
    console.print(
        "[dim]Type /help for commands, Ctrl+C to interrupt, Ctrl+D to quit[/dim]"
    )
    console.print()

    history = FileHistory(str(_get_history_path()))
    session: PromptSession[Any] = PromptSession(
        history=history,
        completer=SlashCompleter(),
        key_bindings=_make_bindings(),
        style=REPL_STYLE,
    )

    branch = _git_branch()

    def get_toolbar() -> list[tuple[str, str]]:
        return _format_session_info(agent, branch)

    renderer = StreamRenderer()
    unsubs: list[object] = [
        agent.on("message_update", renderer.on_message_update),
        agent.on("spell_casting_start", renderer.on_tool_start),
        agent.on("spell_casting_end", renderer.on_tool_end),
    ]

    agent_task: asyncio.Task[Any] | None = None

    def _on_sigint(sig: int, frame: Any) -> None:
        if agent_task is not None and not agent_task.done():
            agent_task.cancel()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _on_sigint)

    while True:
        text = await _read_initial_prompt(session, get_toolbar)

        if text is None:
            console.print("\n[dim]Goodbye.[/dim]")
            break

        text = text.strip()
        if not text:
            continue

        if text.startswith("/"):
            action = _handle_command(text, agent, registry)
            if action == ReplAction.EXIT:
                console.print("[dim]Goodbye.[/dim]")
                break
            if action == ReplAction.SWITCH_MODEL:
                try:
                    await agent.switch_model(agent._model_id)
                except ValueError as e:
                    console.print(f"[red]{e}[/red]")
                    continue
                console.print(f"[green]Model switched: {agent._model_id}[/green]")
                continue
            if action == ReplAction.NEW_SESSION:
                console.print("[yellow]Starting a new session...[/yellow]")
                await agent.close()
                agent._initialized = False
                await agent.initialize()
                console.print(f"[green]New session: {agent.session_id}[/green]")
            continue

        renderer.reset()
        agent_task = asyncio.create_task(agent.run(text))
        try:
            await agent_task
        except asyncio.CancelledError:
            renderer.finish(error=True)
            console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as exc:
            renderer.finish(error=True)
            markup = _render_exception(exc) or f"[red]Error: {exc}[/red]"
            console.print(f"\n{markup}")
        else:
            renderer.finish()
        finally:
            agent_task = None

    for unsub in unsubs:
        if callable(unsub):
            unsub()
    await agent.close()
