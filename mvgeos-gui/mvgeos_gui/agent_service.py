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
    Artifact,
    ArtifactType,
    BackgroundTask,
    ChatMessage,
    CommandExecution,
    ExecutionStep,
    FileExploration,
    StepType,
    TaskStatus,
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
        self._invoked_skill_names: set[str] = set()
        self._loaded_skill_names: set[str] = set()

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
        else:
            from coding_mvge.mvge import CodingMvge

            self._agent = CodingMvge(
                api_key=self._api_key or "mock-key",
                tome_dir=state.tome_service.tome_dir,
                tome_resume=state.active_tome_id,
            )

        # When the agent is created, seed active_skills from the runner's
        # loaded skill manifests so the inspector reflects available skills.
        self.populate_skills(self._agent, state)
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
                # Seed active_skills from the agent's loaded skill manifests.
                if self._agent is not None:
                    self.populate_skills(self._agent, target_state)
                target_state.notify()

        elif event.type == MvgeEventType.MESSAGE_UPDATE:
            text = data.get("text", "")
            kind = data.get("kind", "text")
            if text:
                if kind == "contemplation":
                    target_message.contemplation.append(text)
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
                            target_message.contemplation.extend(thoughts)
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
                    or data.get("params", {}).get("path", "")
                )
                if path:
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
                # Reading a SKILL.md file marks that skill as invoked.
                if str(path).endswith("SKILL.md"):
                    self.mark_skill_invoked(str(path), state=target_state)
            else:
                step = self._get_or_create_step(target_message, StepType.WORKED)
                step.spell_name = spell_name
                step.params = data.get("arguments", {})
                step.details.append(f"Executing {spell_name}...")
                elapsed = time.monotonic() - self._start_time
                step.title = f"Worked for {self._format_duration(elapsed)}"
            if target_state is not None:
                target_state.notify()

            # Track long-running spells as background tasks in the inspector.
            if target_state is not None:
                self._track_spell_start(target_state, spell_id, spell_name, data)

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
                    step.result = str(result or error or "")
            if target_state is not None:
                target_state.notify()

            # Finalise the background task entry created on SPELL_CASTING_START.
            if target_state is not None:
                self._track_spell_end(target_state, spell_id, result, error, duration)

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
                    target_message.contemplation.extend(thoughts)
                    target_message.content = cleaned
            target_message.is_streaming = False
            if target_state is not None:
                target_state.is_channeling = False
                target_state.notify()
            self._is_running = False

        elif event.type == MvgeEventType.ARTIFACT_CREATED:
            artifact_data = data.get("artifact", {})
            artifact = Artifact(
                id=str(artifact_data.get("id", "")),
                title=str(artifact_data.get("title", "Untitled Artifact")),
                summary=str(artifact_data.get("summary", "")),
                content=str(artifact_data.get("content", "")),
                artifact_type=ArtifactType(
                    str(artifact_data.get("type", ArtifactType.OTHER))
                ),
                file_paths=[str(p) for p in artifact_data.get("file_paths", [])],
            )
            target_message.artifacts.append(artifact)
            if target_state is not None:
                target_state.add_artifact(artifact)
            if target_state is not None:
                target_state.notify()

    def _get_or_create_step(
        self, message: ChatMessage, step_type: StepType
    ) -> ExecutionStep:
        for s in message.steps:
            if s.step_type == step_type:
                return s
        step = ExecutionStep(step_type=step_type)
        message.steps.append(step)
        return step

    def _track_spell_start(
        self,
        state: AppState,
        spell_id: str,
        spell_name: str,
        data: dict[str, Any],
    ) -> None:
        """Register a long-running spell cast as a background task."""
        if not spell_id:
            return
        parent_id = data.get("parentSpellCastId") or data.get("parentTaskId")
        state.add_background_task(
            task_id=spell_id,
            name=spell_name,
            parent_id=parent_id,
        )

    def _track_spell_end(
        self,
        state: AppState,
        spell_id: str,
        result: Any,
        error: Any,
        duration: float,
    ) -> None:
        """Mark a background spell task complete or errored on SPELL_CASTING_END."""
        if not spell_id:
            return
        status: TaskStatus
        if error:
            status = TaskStatus.ERROR
        elif result is None or result == "":
            status = TaskStatus.COMPLETE
        else:
            status = TaskStatus.COMPLETE
        state.update_background_task(
            spell_id,
            status=status,
            result=str(result or ""),
            error=str(error) if error else None,
        )
        # Cap progress at 100% on completion.
        task = state.get_background_task(spell_id)
        if task is not None and task.status in (
            TaskStatus.COMPLETE,
            TaskStatus.ERROR,
        ):
            task.progress = 100.0

    def register_subagent_task(
        self,
        state: AppState,
        task_id: str,
        name: str,
        *,
        parent_id: str | None = None,
    ) -> BackgroundTask | None:
        """Register a subagent background task in the inspector state."""
        if not task_id or state is None:
            return None
        return state.add_background_task(
            task_id=task_id, name=name, parent_id=parent_id
        )

    def update_subagent_task(
        self,
        state: AppState,
        task_id: str,
        *,
        status: TaskStatus | str | None = None,
        progress: float | None = None,
    ) -> BackgroundTask | None:
        """Update a subagent background task's status/progress."""
        return state.update_background_task(task_id, status=status, progress=progress)

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
        self.reset_skill_tracking()
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

    # --- Skill tracking helpers ---

    def _runner_skills(self, agent: Any) -> list[Any]:
        """Return the list of SkillManifest from the agent's RuneRunner."""
        runner = getattr(agent, "runner", None)
        if runner is None:
            return []
        getter = getattr(runner, "get_skills", None)
        if not callable(getter):
            return []
        try:
            return list(getter())
        except Exception:
            logger.debug("Failed to read skills from runner", exc_info=True)
            return []

    def populate_skills(self, agent: Any, state: AppState | None) -> None:
        """Seed state.active_skills from the agent's loaded skill manifests.

        Idempotent: skills already tracked are not duplicated. Skills that
        were previously invoked remain marked as invoked.
        """
        if state is None:
            return
        manifests = self._runner_skills(agent)
        for manifest in manifests:
            name = getattr(manifest, "name", "")
            if not name:
                continue
            if name in self._loaded_skill_names:
                continue
            self._loaded_skill_names.add(name)
            state.add_skill(manifest)
        if state.active_skills:
            state.notify()

    def mark_skill_invoked(self, path: str, state: AppState | None = None) -> None:
        """Record that a skill was invoked by reading one of its files."""
        if not path:
            return
        normalized = str(path)
        target_state = state or self._active_state
        if target_state is None:
            return
        for skill in target_state.active_skills:
            if not skill.path:
                continue
            skill_root = skill.path.rstrip("/")
            skill_md = f"{skill_root}/SKILL.md"
            matched = (
                normalized == skill.path
                or normalized == skill_md
                or normalized.startswith(skill_root + "/")
            )
            if matched and skill.name not in self._invoked_skill_names:
                self._invoked_skill_names.add(skill.name)
                skill.invoked = True
                target_state.notify()

    def reset_skill_tracking(self) -> None:
        """Clear per-session skill invocation tracking."""
        self._invoked_skill_names.clear()
        self._loaded_skill_names.clear()
