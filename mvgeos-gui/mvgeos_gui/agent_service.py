"""Agent service layer connecting GUI to CodingMvge and MvgeHarness."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mvgeos_agent.errors import AuthenticationError
from mvgeos_agent.types import MvgeEvent, MvgeEventType

from mvgeos_gui.models import (
    ChatMessage,
    CommandExecution,
    ExecutionStep,
    FileExploration,
    StepType,
    extract_contemplation_tags,
)

if TYPE_CHECKING:
    from coding_mvge.mvge import CodingMvge

    from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


def resolve_api_key(explicit_key: str | None = None) -> str | None:
    """Resolve OpenRouter API key from explicit arg, env vars, or auth file."""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    env_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("MVGEOS_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    with contextlib.suppress(Exception):
        from mvgeos_cli.auth import load_api_key_from_auth

        auth_key = load_api_key_from_auth()
        if auth_key and auth_key.strip():
            return auth_key.strip()
    return None


class AgentService:
    """Service bridge managing agent runtime lifecycle and event sink for GUI."""

    def __init__(
        self,
        project_path: Path,
        api_key: str | None = None,
        agent_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._project_path = project_path
        self._api_key = resolve_api_key(api_key)
        self._agent_factory = agent_factory
        self._agent: CodingMvge | None = None
        self._active_message: ChatMessage | None = None
        self._active_state: AppState | None = None
        self._is_running = False
        self._active_task: asyncio.Task[Any] | None = None
        self._start_time: float = 0.0
        self._pending_spell_starts: dict[str, float] = {}

    @property
    def project_path(self) -> Path:
        return self._project_path

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_or_create_agent(self, state: AppState) -> Any:
        """Instantiate or retrieve the bound CodingMvge instance."""
        if self._agent is not None:
            return self._agent

        if self._agent_factory is not None:
            self._agent = self._agent_factory(
                project_path=self._project_path,
                api_key=self._api_key or "mock-key",
                state=state,
            )
            return self._agent

        from coding_mvge.mvge import CodingMvge

        self._agent = CodingMvge(
            api_key=self._api_key or "mock-key",
            session_dir=state.tome_service.tome_dir,
            session_resume=state.active_tome_id,
        )
        return self._agent

    def _ensure_listeners(self, agent: Any) -> None:
        """Attach event listeners to the agent instance only once."""
        if (
            hasattr(agent, "on")
            and getattr(agent, "_gui_listeners_bound", False) is not True
        ):
            for event_type in MvgeEventType:
                agent.on(
                    event_type,
                    lambda e: self.handle_event(e),
                )
            agent._gui_listeners_bound = True

    def handle_event(
        self,
        event: MvgeEvent,
        message: ChatMessage | None = None,
        state: AppState | None = None,
    ) -> None:
        """Process an MvgeEvent and update reactive ChatMessage and AppState."""
        target_message = message or self._active_message
        target_state = state or self._active_state
        if target_message is None:
            return

        data = event.data

        if event.type == MvgeEventType.AGENT_START:
            self._start_time = time.monotonic()
            target_message.is_streaming = True
            if target_state is not None:
                target_state.is_channeling = True
                target_state.notify()

        elif event.type == MvgeEventType.MESSAGE_UPDATE:
            text = data.get("text", "")
            kind = data.get("kind", "text")
            if text:
                if kind == "contemplation":
                    target_message.contemplation += text
                else:
                    target_message.content += text
                    if (
                        "<think>" in target_message.content
                        or "<thought>" in target_message.content
                    ):
                        cleaned, thoughts = extract_contemplation_tags(
                            target_message.content
                        )
                        if thoughts:
                            sep = "\n\n" if target_message.contemplation else ""
                            target_message.contemplation = (
                                f"{target_message.contemplation}{sep}{thoughts}"
                            )
                            target_message.content = cleaned
                target_message.is_streaming = True
                if target_state is not None:
                    target_state.notify()

        elif event.type == MvgeEventType.AFTER_PROVIDER_RESPONSE:
            mana = data.get("mana_used", 0)
            if isinstance(mana, int) and mana > 0:
                target_message.mana_used = mana
                if target_state is not None:
                    target_state.total_mana_used = mana
                    target_state.notify()

        elif event.type == MvgeEventType.SPELL_CASTING_START:
            spell_id = data.get("spellCastId", "")
            spell_name = data.get("spellName", "tool")
            self._pending_spell_starts[spell_id] = time.monotonic()

            if spell_name == "bash":
                cmd = data.get("command") or data.get("params", {}).get("command", "")
                step = self._get_or_create_step(target_message, StepType.COMMANDS)
                step.commands.append(
                    CommandExecution(
                        command=str(cmd) if cmd else "$ (running command...)",
                    )
                )
                step.title = f"Ran {len(step.commands)} command(s)"
            elif spell_name in ("read", "grep", "find", "list"):
                path = (
                    data.get("path")
                    or data.get("file_path")
                    or data.get("params", {}).get("path", "file")
                )
                lines = data.get("lines") or data.get("params", {}).get("lines")
                step = self._get_or_create_step(target_message, StepType.FILES)
                step.files.append(
                    FileExploration(
                        path=str(path),
                        operation=spell_name,
                        lines=str(lines) if lines else None,
                    )
                )
                step.title = f"Explored {len(step.files)} file(s)"
            else:
                step = self._get_or_create_step(target_message, StepType.WORKED)
                step.details.append(f"Executing {spell_name}...")
                elapsed = time.monotonic() - self._start_time
                step.title = f"Worked for {self._format_duration(elapsed)}"
            if target_state is not None:
                target_state.notify()

        elif event.type == MvgeEventType.SPELL_CASTING_END:
            spell_id = data.get("spellCastId", "")
            start_ts = self._pending_spell_starts.pop(spell_id, time.monotonic())
            duration = max(0.0, time.monotonic() - start_ts)
            result = data.get("result", "")
            error = data.get("error")

            for step in target_message.steps:
                if step.step_type == StepType.COMMANDS and step.commands:
                    last_cmd = step.commands[-1]
                    if not last_cmd.output and not last_cmd.is_error:
                        last_cmd.output = str(result or error or "")
                        last_cmd.is_error = error is not None
                        last_cmd.duration_seconds = duration
                        break
                elif step.step_type == StepType.FILES and step.files:
                    last_file = step.files[-1]
                    if not last_file.details and not last_file.is_error:
                        last_file.details = str(result or error or "")
                        last_file.is_error = error is not None
                        break
                elif step.step_type == StepType.WORKED:
                    step.duration_seconds = time.monotonic() - self._start_time
                    step.title = (
                        f"Worked for {self._format_duration(step.duration_seconds)}"
                    )
            if target_state is not None:
                target_state.notify()

        elif event.type in (MvgeEventType.TURN_END, MvgeEventType.AGENT_END):
            if self._start_time > 0:
                elapsed = max(0.0, time.monotonic() - self._start_time)
                for step in target_message.steps:
                    if step.step_type == StepType.WORKED:
                        step.duration_seconds = elapsed
                        step.title = f"Worked for {self._format_duration(elapsed)}"
                        step.is_complete = True
            if target_message.content:
                cleaned, thoughts = extract_contemplation_tags(target_message.content)
                if thoughts:
                    sep = "\n\n" if target_message.contemplation else ""
                    target_message.contemplation = (
                        f"{target_message.contemplation}{sep}{thoughts}"
                    )
                    target_message.content = cleaned
            target_message.is_streaming = False
            if target_state is not None:
                target_state.is_channeling = False
                target_state.notify()
            self._is_running = False

    def _get_or_create_step(
        self, message: ChatMessage, step_type: StepType
    ) -> ExecutionStep:
        for s in message.steps:
            if s.step_type == step_type:
                return s
        step = ExecutionStep(step_type=step_type)
        message.steps.append(step)
        return step

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds < 1.0:
            return f"{seconds:.1f}s"
        if seconds < 60.0:
            return f"{seconds:.1f}s"
        mins = int(seconds // 60)
        rem_secs = seconds % 60
        return f"{mins}m {rem_secs:.0f}s"

    async def run_prompt(
        self, prompt: str, state: AppState, message: ChatMessage
    ) -> None:
        """Run agent with prompt asynchronously while capturing all events."""
        self._is_running = True
        self._active_message = message
        self._active_state = state
        self._start_time = time.monotonic()
        self._pending_spell_starts.clear()
        state.is_channeling = True
        message.is_streaming = True
        state.notify()

        if not self._api_key:
            message.is_error = True
            message.error_message = "API key required"
            message.content = (
                "**Authentication Required**: No OpenRouter API key was found.\n\n"
                "Please set the `OPENROUTER_API_KEY` environment variable, "
                "run `mvgeos setup`, or pass `--api-key` when starting `mvgeos-gui`."
            )
            message.is_streaming = False
            state.is_channeling = False
            self._is_running = False
            self._active_message = None
            self._active_state = None
            state.notify()
            return

        try:
            agent = self.get_or_create_agent(state)
            self._ensure_listeners(agent)

            if hasattr(agent, "switch_model") and state.selected_model:
                await agent.switch_model(state.selected_model)

            await agent.run(prompt)
        except asyncio.CancelledError:
            logger.info("Agent run cancelled by summoner")
            message.content += "\n\n*(Cancelled by summoner)*"
        except AuthenticationError as exc:
            logger.exception("Authentication failed: %s", exc)
            message.is_error = True
            message.error_message = str(exc)
            message.content = (
                "**Authentication Failed (HTTP 401)**: The OpenRouter API key "
                "is invalid or unauthorized.\n\n"
                "Please check your `OPENROUTER_API_KEY` environment variable "
                "or re-run `mvgeos setup`."
            )
        except Exception as exc:
            logger.exception("Error executing agent prompt: %s", exc)
            message.is_error = True
            message.error_message = str(exc)
            if not message.content:
                message.content = f"Execution error: {exc}"
        finally:
            message.is_streaming = False
            state.is_channeling = False
            self._is_running = False
            self._active_message = None
            self._active_state = None
            state.notify()

    def cancel(self) -> None:
        """Cancel active channeling task if running."""
        if self._active_task is not None:
            with contextlib.suppress(Exception):
                self._active_task.cancel()
        self._is_running = False
        self._active_message = None
        self._active_state = None
