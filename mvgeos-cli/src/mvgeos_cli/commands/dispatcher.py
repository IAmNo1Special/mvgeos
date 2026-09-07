from __future__ import annotations

from collections.abc import Callable

from mvgeos_agent.protocol import MvgeAgent
from mvgeos_agent.types import QueueMode
from mvgeos_provider.model_registry import ModelRegistry
from rich.console import Console

from mvgeos_cli.formatting import format_error

_console = Console()

SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show this help message",
    "/quit": "Exit the REPL",
    "/exit": "Exit the REPL",
    "/model": "Switch or list models: /model [id] or /model --free",
    "/models": "List available models: /models [--free]",
    "/mode": "Toggle queue mode (all/one-at-a-time): /mode or /m",
    "/new": "Start a new tome",
    "/tome": "Show current tome info",
    "/resume": "Resume a previous tome: /resume <path>",
    "/spells": "List or set enabled spells: /spells [comma-separated]",
    "/steer": "Steer agent mid-run: /steer <message>",
    "/followup": "Queue follow-up for post-run: /followup <message>",
    "/refresh-models": "Refresh model catalog from OpenRouter API",
}


class CommandDispatcher:
    """Deep module executing interactive slash commands against MvgeAgent."""

    def __init__(
        self,
        agent: MvgeAgent,
        registry: ModelRegistry,
        out: Callable[[str], None] = _console.print,
    ) -> None:
        self._agent = agent
        self._registry = registry
        self._out = out

    @property
    def agent(self) -> MvgeAgent:
        return self._agent

    @agent.setter
    def agent(self, value: MvgeAgent) -> None:
        self._agent = value

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @registry.setter
    def registry(self, value: ModelRegistry) -> None:
        self._registry = value

    async def dispatch(
        self, command: str, out: Callable[[str], None] | None = None
    ) -> bool:
        """Execute a slash command.

        Returns:
            bool: True if the interactive session should exit, False otherwise.
        """
        output = out if out is not None else self._out
        parts = command.strip().split(maxsplit=1)
        if not parts:
            return False
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            return True

        if cmd == "/help":
            output("[bold]Available commands:[/bold]")
            for name, desc in SLASH_COMMANDS.items():
                output(f"  [cyan]{name:<15}[/cyan] {desc}")
            return False

        if cmd == "/tome":
            tid = self._agent.tome_id or "none"
            output(f"[dim]Tome ID: {tid}[/dim]")
            output(f"[dim]Model: {self._agent.model_id}[/dim]")
            spells = getattr(self._agent, "enabled_spells", [])
            output(f"[bold]Enabled spells:[/bold] {', '.join(spells) or 'none'}")
            providers = getattr(self._agent, "registered_providers", [])
            output(f"[dim]Providers: {', '.join(providers) or 'none'}[/dim]")
            return False

        if cmd in ("/model", "/models"):
            stripped = args.strip()
            if not stripped or stripped in ("--free", "-f"):
                output(f"[bold]Current model:[/bold] {self._agent.model_id}")
                output("[bold]Available models:[/bold]")
                all_models = self._registry.list_all()
                if stripped in ("--free", "-f"):
                    all_models = [
                        m
                        for m in all_models
                        if getattr(m, "is_free", getattr(m, "free", False))
                    ]
                for m in all_models:
                    is_free = getattr(m, "is_free", getattr(m, "free", False))
                    tag = " [green](free)[/green]" if is_free else ""
                    output(f"  {m.id}{tag}")
                output("[dim]Try /refresh-models to fetch the latest catalog[/dim]")
                return False

            candidate = stripped
            if self._registry.get(candidate) is None:
                output(format_error(f"Unknown model: {candidate}"))
                output("[dim]Try /refresh-models to fetch the latest catalog[/dim]")
                return False

            try:
                if hasattr(self._agent, "switch_model") and callable(
                    self._agent.switch_model
                ):
                    await self._agent.switch_model(candidate)
                elif hasattr(self._agent, "_model_id"):
                    object.__setattr__(self._agent, "_model_id", candidate)
            except Exception as e:
                output(format_error(e))
                return False
            output(f"[green]Model switched: {candidate}[/green]")
            return False

        if cmd == "/refresh-models":
            output("[yellow]Fetching latest models from OpenRouter...[/yellow]")
            try:
                count = await self._registry.refresh(force_refresh=True)
            except Exception as exc:
                output(format_error(f"Failed to refresh models: {exc}"))
            else:
                output(f"[green]Models refreshed ({count} new models).[/green]")
            return False

        if cmd == "/spells":
            if args:
                new_spells = [s.strip() for s in args.split(",") if s.strip()]
                if hasattr(self._agent, "set_enabled_spells") and callable(
                    self._agent.set_enabled_spells
                ):
                    self._agent.set_enabled_spells(new_spells)
                elif hasattr(self._agent, "_spell_names"):
                    object.__setattr__(self._agent, "_spell_names", new_spells)
                output(f"[green]Spells set to: {', '.join(new_spells)}[/green]")
            else:
                enabled = getattr(self._agent, "enabled_spells", [])
                available = getattr(self._agent, "available_spells", enabled)
                if enabled:
                    output(f"[bold]Enabled spells:[/bold] {', '.join(enabled)}")
                other = [s for s in available if s not in enabled]
                if other:
                    output(f"[dim]Available inactive spells:[/dim] {', '.join(other)}")
                if not enabled and not other:
                    output("[dim]No spells available[/dim]")
            return False

        if cmd in ("/mode", "/m"):
            current_mode = self._agent.queue_mode
            new_mode = (
                QueueMode.ALL
                if current_mode == QueueMode.ONE_AT_A_TIME
                else QueueMode.ONE_AT_A_TIME
            )
            self._agent.queue_mode = new_mode
            output(f"[dim]Queue mode: {self._agent.queue_mode}[/dim]")
            return False

        if cmd in ("/steer", "/s"):
            if args:
                self._agent.steer(args.strip())
                output(f"[dim]Steering queued: {args.strip()}[/dim]")
            return False

        if cmd in ("/followup", "/f", "/follow"):
            if args:
                self._agent.follow_up(args.strip())
                output(f"[dim]Follow-up queued: {args.strip()}[/dim]")
            else:
                output(f"[dim]Queue mode: {self._agent.queue_mode}[/dim]")
            return False

        if cmd == "/new":
            output("[yellow]Starting a new session...[/yellow]")
            try:
                if hasattr(self._agent, "reset_session") and callable(
                    self._agent.reset_session
                ):
                    await self._agent.reset_session(resume_tome_id=None)
                else:
                    await self._agent.close()
                    if hasattr(self._agent, "_initialized"):
                        object.__setattr__(self._agent, "_initialized", False)
                    await self._agent.initialize()
            except Exception as e:
                output(format_error(e))
                return False
            output(f"[green]New tome: {self._agent.tome_id}[/green]")
            return False

        if cmd == "/resume":
            if args:
                target_path = args.strip()
                output(f"[yellow]Resuming tome {target_path}...[/yellow]")
                try:
                    if hasattr(self._agent, "reset_session") and callable(
                        self._agent.reset_session
                    ):
                        await self._agent.reset_session(resume_tome_id=target_path)
                    else:
                        if hasattr(self._agent, "_tome_resume"):
                            object.__setattr__(self._agent, "_tome_resume", target_path)
                        await self._agent.close()
                        if hasattr(self._agent, "_initialized"):
                            object.__setattr__(self._agent, "_initialized", False)
                        await self._agent.initialize()
                except Exception as e:
                    output(format_error(e))
                    return False
                output(f"[green]Resumed tome: {self._agent.tome_id}[/green]")
                return False
            output(format_error("Usage: /resume <path-to-tome.jsonl>"))
            return False

        output(format_error(f"Unknown command: {cmd}"))
        output("[dim]Type /help for available commands[/dim]")
        return False
