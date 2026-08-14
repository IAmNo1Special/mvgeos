"""Agent service layer connecting GUI to CodingMvge and MvgeHarness."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mvgeos_agent.types import MvgeEvent, MvgeEventType

from mvgeos_gui.models import (
    ChatMessage,
    CommandExecution,
    ExecutionStep,
    FileExploration,
    StepType,
)

if TYPE_CHECKING:
    from coding_mvge.mvge import CodingMvge

    from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


class AgentService:
    """Service bridge managing agent runtime lifecycle and event sink for GUI."""

    def __init__(
        self,
        project_path: Path,
        api_key: str = "openrouter-mock-key",
        agent_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._project_path = project_path
        self._api_key = api_key
        self._agent_factory = agent_factory
        self._agent: CodingMvge | None = None
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
                api_key=self._api_key,
                state=state,
            )
            return self._agent

        from coding_mvge.mvge import CodingMvge

        self._agent = CodingMvge(
            api_key=self._api_key,
            session_dir=state.tome_service.tome_dir,
            session_resume=state.active_tome_id,
        )
        return self._agent

    def handle_event(
        self, event: MvgeEvent, message: ChatMessage, state: AppState
    ) -> None:
        """Process an MvgeEvent and update the reactive ChatMessage and AppState."""
        data = event.data

        if event.type == MvgeEventType.AGENT_START:
            self._start_time = time.monotonic()
            message.is_streaming = True
            state.is_channeling = True
            state.notify()

        elif event.type == MvgeEventType.MESSAGE_UPDATE:
            text = data.get("text", "")
            if text:
                message.content += text
                message.is_streaming = True
                state.notify()

        elif event.type == MvgeEventType.AFTER_PROVIDER_RESPONSE:
            mana = data.get("mana_used", 0)
            if isinstance(mana, int) and mana > 0:
                message.mana_used = mana
                state.total_mana_used = mana
                state.notify()

        elif event.type == MvgeEventType.SPELL_CASTING_START:
            spell_id = data.get("spellCastId", "")
            spell_name = data.get("spellName", "tool")
            self._pending_spell_starts[spell_id] = time.monotonic()

            if spell_name == "bash":
                cmd = data.get("command") or data.get("params", {}).get("command", "")
                step = self._get_or_create_step(message, StepType.COMMANDS)
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
                step = self._get_or_create_step(message, StepType.FILES)
                step.files.append(
                    FileExploration(
                        path=str(path),
                        operation=spell_name,
                        lines=str(lines) if lines else None,
                    )
                )
                step.title = f"Explored {len(step.files)} file(s)"
            else:
                step = self._get_or_create_step(message, StepType.WORKED)
                step.details.append(f"Executing {spell_name}...")
                elapsed = time.monotonic() - self._start_time
                step.title = f"Worked for {self._format_duration(elapsed)}"
            state.notify()

        elif event.type == MvgeEventType.SPELL_CASTING_END:
            spell_id = data.get("spellCastId", "")
            start_ts = self._pending_spell_starts.pop(spell_id, time.monotonic())
            duration = max(0.0, time.monotonic() - start_ts)
            result = data.get("result", "")
            error = data.get("error")

            for step in message.steps:
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
            state.notify()

        elif event.type in (MvgeEventType.TURN_END, MvgeEventType.AGENT_END):
            if self._start_time > 0:
                elapsed = max(0.0, time.monotonic() - self._start_time)
                for step in message.steps:
                    if step.step_type == StepType.WORKED:
                        step.duration_seconds = elapsed
                        step.title = f"Worked for {self._format_duration(elapsed)}"
                        step.is_complete = True
            message.is_streaming = False
            state.is_channeling = False
            self._is_running = False
            state.notify()

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
        self._start_time = time.monotonic()
        state.is_channeling = True
        message.is_streaming = True
        state.notify()

        try:
            agent = self.get_or_create_agent(state)
            if hasattr(agent, "on"):
                for event_type in MvgeEventType:
                    agent.on(
                        event_type,
                        lambda e: self.handle_event(e, message, state),
                    )

            if hasattr(agent, "switch_model") and state.selected_model:
                await agent.switch_model(state.selected_model)

            await agent.run(prompt)
        except asyncio.CancelledError:
            logger.info("Agent run cancelled by summoner")
            message.content += "\n\n*(Cancelled by summoner)*"
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
            state.notify()

    def cancel(self) -> None:
        """Cancel active channeling task if running."""
        if self._active_task is not None:
            with contextlib.suppress(Exception):
                self._active_task.cancel()
        self._is_running = False
