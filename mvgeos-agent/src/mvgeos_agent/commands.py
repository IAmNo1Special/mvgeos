from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from mvgeos_provider.model_registry import ModelRegistry

from mvgeos_agent.protocol import MvgeAgent
from mvgeos_agent.types import QueueMode

logger = logging.getLogger(__name__)

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


class CommandAction(StrEnum):
    """Enumeration of structured actions produced by slash command dispatch."""

    EXIT = "exit"
    HELP = "help"
    TOME_INFO = "tome_info"
    MODELS_LISTED = "models_listed"
    MODEL_SWITCHED = "model_switched"
    CATALOG_REFRESHED = "catalog_refreshed"
    SPELLS_LISTED = "spells_listed"
    SPELLS_UPDATED = "spells_updated"
    QUEUE_MODE_CHANGED = "queue_mode_changed"
    STEERING_QUEUED = "steering_queued"
    FOLLOWUP_QUEUED = "followup_queued"
    SESSION_RESET = "session_reset"
    SESSION_RESUMED = "session_resumed"
    INFO = "info"
    ERROR = "error"


@dataclass(frozen=True)
class CommandOutcome:
    """The structured result of dispatching an interactive slash command."""

    command: str
    action: CommandAction
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    should_exit: bool = False


class CommandDispatcher:
    """Deep module for executing interactive slash commands against MvgeAgent."""

    def __init__(
        self,
        agent: MvgeAgent,
        registry: ModelRegistry | None = None,
    ) -> None:
        self._agent = agent
        self._registry = registry or getattr(agent, "model_registry", None)

    @property
    def agent(self) -> MvgeAgent:
        return self._agent

    @agent.setter
    def agent(self, value: MvgeAgent) -> None:
        self._agent = value

    @property
    def registry(self) -> ModelRegistry | None:
        return self._registry

    @registry.setter
    def registry(self, value: ModelRegistry | None) -> None:
        self._registry = value

    async def dispatch(self, command: str) -> CommandOutcome:
        """Execute a slash command and return a structured outcome.

        Args:
            command: The command line string (e.g. '/model google/gemini-2.5-flash').

        Returns:
            CommandOutcome: The structured action, payload data, and display message.
        """
        parts = command.strip().split(maxsplit=1)
        if not parts:
            return CommandOutcome(
                command="",
                action=CommandAction.INFO,
                message="Type /help for available commands",
            )

        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            return CommandOutcome(
                command=cmd,
                action=CommandAction.EXIT,
                should_exit=True,
                message="Session ended.",
            )

        if cmd == "/help":
            lines = ["Available commands:"]
            for name, desc in SLASH_COMMANDS.items():
                lines.append(f"  {name:<16} {desc}")
            return CommandOutcome(
                command=cmd,
                action=CommandAction.HELP,
                data={"commands": SLASH_COMMANDS},
                message="\n".join(lines),
            )

        if cmd == "/tome":
            tid = self._agent.tome_id or "none"
            model = self._agent.model_id
            spells = self._agent.enabled_spells
            providers = self._agent.registered_providers
            lines = [
                f"Tome ID: {tid}",
                f"Model: {model}",
                f"Enabled spells: {', '.join(spells) or 'none'}",
                f"Providers: {', '.join(providers) or 'none'}",
            ]
            return CommandOutcome(
                command=cmd,
                action=CommandAction.TOME_INFO,
                data={
                    "tome_id": tid,
                    "model_id": model,
                    "enabled_spells": spells,
                    "providers": providers,
                },
                message="\n".join(lines),
            )

        if cmd in ("/model", "/models"):
            stripped = args.strip()
            if not stripped or stripped in ("--free", "-f"):
                if self._registry is None:
                    return CommandOutcome(
                        command=cmd,
                        action=CommandAction.ERROR,
                        data={"error": "Model registry unavailable"},
                        message="Model registry unavailable",
                    )
                all_models = self._registry.list_all()
                is_free_only = stripped in ("--free", "-f")
                if is_free_only:
                    all_models = [
                        m
                        for m in all_models
                        if getattr(m, "is_free", getattr(m, "free", False))
                    ]
                lines = [
                    f"Current model: {self._agent.model_id}",
                    "Available models:",
                ]
                for m in all_models:
                    is_free = getattr(m, "is_free", getattr(m, "free", False))
                    tag = " (free)" if is_free else ""
                    lines.append(f"  {m.id}{tag}")
                lines.append("Try /refresh-models to fetch the latest catalog")
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.MODELS_LISTED,
                    data={
                        "models": all_models,
                        "is_free_only": is_free_only,
                        "current_model": self._agent.model_id,
                    },
                    message="\n".join(lines),
                )

            candidate = stripped
            if self._registry is not None and self._registry.get(candidate) is None:
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.ERROR,
                    data={
                        "error": f"Unknown model: {candidate}",
                        "candidate": candidate,
                    },
                    message=(
                        f"Unknown model: {candidate}\n"
                        "Try /refresh-models to fetch the latest catalog"
                    ),
                )

            try:
                await self._agent.switch_model(candidate)
            except Exception as e:
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.ERROR,
                    data={"error": str(e), "candidate": candidate},
                    message=f"Failed to switch model: {e}",
                )

            return CommandOutcome(
                command=cmd,
                action=CommandAction.MODEL_SWITCHED,
                data={"model_id": candidate},
                message=f"Model switched: {candidate}",
            )

        if cmd == "/refresh-models":
            if self._registry is None:
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.ERROR,
                    data={"error": "Model registry unavailable"},
                    message="Model registry unavailable",
                )
            try:
                count = await self._registry.refresh(force_refresh=True)
            except Exception as exc:
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.ERROR,
                    data={"error": str(exc)},
                    message=f"Failed to refresh models: {exc}",
                )
            return CommandOutcome(
                command=cmd,
                action=CommandAction.CATALOG_REFRESHED,
                data={"new_models_count": count},
                message=f"Models refreshed ({count} new models).",
            )

        if cmd == "/spells":
            if args:
                new_spells = [s.strip() for s in args.split(",") if s.strip()]
                self._agent.set_enabled_spells(new_spells)
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.SPELLS_UPDATED,
                    data={"enabled_spells": new_spells},
                    message=f"Spells set to: {', '.join(new_spells)}",
                )

            enabled = self._agent.enabled_spells
            available = self._agent.available_spells
            lines = []
            if enabled:
                lines.append(f"Enabled spells: {', '.join(enabled)}")
            other = [s for s in available if s not in enabled]
            if other:
                lines.append(f"Available inactive spells: {', '.join(other)}")
            if not enabled and not other:
                lines.append("No spells available")
            return CommandOutcome(
                command=cmd,
                action=CommandAction.SPELLS_LISTED,
                data={"enabled_spells": enabled, "available_spells": available},
                message="\n".join(lines),
            )

        if cmd in ("/mode", "/m"):
            current_mode = self._agent.queue_mode
            new_mode = (
                QueueMode.ALL
                if current_mode == QueueMode.ONE_AT_A_TIME
                else QueueMode.ONE_AT_A_TIME
            )
            self._agent.queue_mode = new_mode
            return CommandOutcome(
                command=cmd,
                action=CommandAction.QUEUE_MODE_CHANGED,
                data={"queue_mode": new_mode},
                message=f"Queue mode: {new_mode}",
            )

        if cmd in ("/steer", "/s"):
            if args:
                self._agent.steer(args.strip())
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.STEERING_QUEUED,
                    data={"message": args.strip()},
                    message=f"Steering queued: {args.strip()}",
                )
            return CommandOutcome(
                command=cmd,
                action=CommandAction.ERROR,
                data={"error": "Usage: /steer <message>"},
                message="Usage: /steer <message>",
            )

        if cmd in ("/followup", "/f", "/follow"):
            if args:
                self._agent.follow_up(args.strip())
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.FOLLOWUP_QUEUED,
                    data={"message": args.strip()},
                    message=f"Follow-up queued: {args.strip()}",
                )
            return CommandOutcome(
                command=cmd,
                action=CommandAction.INFO,
                data={"queue_mode": self._agent.queue_mode},
                message=f"Queue mode: {self._agent.queue_mode}",
            )

        if cmd == "/new":
            try:
                await self._agent.reset_session(resume_tome_id=None)
            except Exception as e:
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.ERROR,
                    data={"error": str(e)},
                    message=f"Failed to start new tome: {e}",
                )
            return CommandOutcome(
                command=cmd,
                action=CommandAction.SESSION_RESET,
                data={"tome_id": self._agent.tome_id},
                message=f"New tome: {self._agent.tome_id}",
            )

        if cmd == "/resume":
            if args:
                target_path = args.strip()
                try:
                    await self._agent.reset_session(resume_tome_id=target_path)
                except Exception as e:
                    return CommandOutcome(
                        command=cmd,
                        action=CommandAction.ERROR,
                        data={"error": str(e), "path": target_path},
                        message=f"Failed to resume tome: {e}",
                    )
                return CommandOutcome(
                    command=cmd,
                    action=CommandAction.SESSION_RESUMED,
                    data={"tome_id": self._agent.tome_id, "path": target_path},
                    message=f"Resumed tome: {self._agent.tome_id}",
                )
            return CommandOutcome(
                command=cmd,
                action=CommandAction.ERROR,
                data={"error": "Usage: /resume <path-to-tome.jsonl>"},
                message="Usage: /resume <path-to-tome.jsonl>",
            )

        return CommandOutcome(
            command=cmd,
            action=CommandAction.ERROR,
            data={"error": f"Unknown command: {cmd}"},
            message=f"Unknown command: {cmd}\nType /help for available commands",
        )


__all__ = [
    "SLASH_COMMANDS",
    "CommandAction",
    "CommandDispatcher",
    "CommandOutcome",
]
