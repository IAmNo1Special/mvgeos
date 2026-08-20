"""Application state management for mvgeos-gui."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_runes.loader import get_default_skill_paths, load_skills_from_paths
from mvgeos_runes.types import SkillManifest
from mvgeos_tome.types import TomeEntryType

from mvgeos_gui.agent_service import AgentService
from mvgeos_gui.autocomplete import (
    AutocompleteService,
    MentionChip,
    MentionIndex,
    SlashCommandRegistry,
)
from mvgeos_gui.config_service import ConfigService
from mvgeos_gui.git_diff import ChangedFile, get_changed_files, get_diff_for_file
from mvgeos_gui.models import (
    Artifact,
    BackgroundTask,
    ChatMessage,
    ExecutionStep,
    MessagePart,
    MessagePartType,
    SkillInfo,
    StepType,
    TaskStatus,
    extract_contemplation_tags,
    extract_ordered_content,
)
from mvgeos_gui.tome_service import TomeListEntry, TomeService

logger = logging.getLogger(__name__)


def _extract_parts_and_content(
    content: Any,
) -> tuple[str, list[str], list[MessagePart]]:
    """Extract text, contemplation list, and sequential MessageParts.

    Returns (plain_text, contemplation_list, sequential_parts).
    """
    parts: list[MessagePart] = []
    text_parts: list[str] = []
    thought_parts: list[str] = []

    if isinstance(content, str):
        cleaned, thoughts = extract_contemplation_tags(content)
        ordered = extract_ordered_content(content)
        if ordered:
            for item in ordered:
                itype = item.get("type")
                itext = item.get("text", "")
                if not itext:
                    continue
                if itype == "thought":
                    parts.append(
                        MessagePart(part_type=MessagePartType.CONTEMPLATION, text=itext)
                    )
                else:
                    parts.append(
                        MessagePart(part_type=MessagePartType.TEXT, text=itext)
                    )
        elif cleaned or thoughts:
            for t in thoughts:
                parts.append(
                    MessagePart(part_type=MessagePartType.CONTEMPLATION, text=t)
                )
            if cleaned:
                parts.append(MessagePart(part_type=MessagePartType.TEXT, text=cleaned))
        return cleaned, thoughts, parts

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type in ("contemplation", "thinking"):
                    t_text = str(item.get("text", "") or item.get("thinking", ""))
                    if t_text:
                        thought_parts.append(t_text)
                        parts.append(
                            MessagePart(
                                part_type=MessagePartType.CONTEMPLATION,
                                text=t_text,
                            )
                        )
                elif item_type == "text":
                    txt = str(item.get("text", ""))
                    if txt:
                        cleaned, tag_thoughts = extract_contemplation_tags(txt)
                        if tag_thoughts:
                            thought_parts.extend(tag_thoughts)
                            for t in tag_thoughts:
                                parts.append(
                                    MessagePart(
                                        part_type=MessagePartType.CONTEMPLATION,
                                        text=t,
                                    )
                                )
                        if cleaned:
                            text_parts.append(cleaned)
                            parts.append(
                                MessagePart(
                                    part_type=MessagePartType.TEXT,
                                    text=cleaned,
                                )
                            )
                elif item_type in ("tool_call", "tool_use"):
                    step_type = (
                        StepType.COMMANDS
                        if item.get("name") == "bash"
                        else (
                            StepType.FILES
                            if item.get("name") in ("read", "grep", "find", "list")
                            else StepType.WORKED
                        )
                    )
                    step = ExecutionStep(
                        step_type=step_type,
                        spell_name=str(item.get("name", "")),
                        params=item.get("arguments", {}),
                        is_complete=True,
                    )
                    parts.append(MessagePart(part_type=MessagePartType.STEP, step=step))
                elif "text" in item:
                    txt = str(item["text"])
                    text_parts.append(txt)
                    parts.append(MessagePart(part_type=MessagePartType.TEXT, text=txt))
            elif isinstance(item, str):
                text_parts.append(item)
                parts.append(MessagePart(part_type=MessagePartType.TEXT, text=item))
        return "\n".join(text_parts), [t for t in thought_parts if t], parts

    return str(content or ""), [], parts


def _extract_text_and_contemplation(content: Any) -> tuple[str, list[str]]:
    """Extract plain text and contemplation from message content."""
    text, thoughts, _ = _extract_parts_and_content(content)
    return text, thoughts


@dataclass
class AppState:
    """Reactive state container for MvgeOS desktop GUI session."""

    project_path: Path = field(default_factory=Path.cwd)
    active_tome_id: str | None = None
    tome_title: str = "New Conversation"
    inspector_expanded: bool = True
    selected_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    recent_projects: list[Path] = field(default_factory=list)
    is_channeling: bool = False
    tome_service: TomeService = field(
        default_factory=TomeService, repr=False, compare=False
    )
    loaded_tomes: list[TomeListEntry] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)
    total_mana_used: int = 0
    active_prompt: str = ""
    api_key: str | None = None
    pending_attachments: list[str] = field(default_factory=list)
    selected_mentions: list[MentionChip] = field(default_factory=list)
    active_skills: list[SkillInfo] = field(default_factory=list)
    agent_service: AgentService | None = field(default=None, repr=False, compare=False)
    active_task: asyncio.Task[Any] | None = field(
        default=None, repr=False, compare=False
    )
    background_tasks: list[BackgroundTask] = field(default_factory=list)
    _autocomplete_service: AutocompleteService | None = field(
        default=None, repr=False, compare=False
    )
    _change_listeners: list[Callable[[], Any]] = field(
        default_factory=list, repr=False, compare=False
    )
    _selected_diff_path: str | None = field(default=None, repr=False, compare=False)
    changed_files: list[ChangedFile] = field(default_factory=list)
    _selected_artifact_id: str | None = field(default=None, repr=False, compare=False)
    artifacts: list[Artifact] = field(default_factory=list)
    _config_service: ConfigService = field(
        default_factory=ConfigService, repr=False, compare=False
    )
    _show_app_settings: bool = False
    _show_workspace_settings: bool = False
    current_view: str = "chat"
    sidebar_open: bool = True
    review_open: bool = False
    is_streaming: bool = False
    streaming_content: str = ""
    streaming_thinking: str = ""
    streaming_tool_calls: list = field(default_factory=list)
    session_loading: bool = False
    pi_status: str = "idle"
    terminal_open: bool = False
    chat_side_panel: str | None = None
    _sidebar_width: int = 260
    _review_width: int = 320
    _command_palette_open: bool = False

    def __post_init__(self) -> None:
        """Initialize state invariants."""
        if not self.recent_projects and self.project_path:
            self.recent_projects.append(self.project_path)

    @property
    def uploaded_files(self) -> list[str]:
        """Files attached as context for the current session."""
        return self.pending_attachments

    def subscribe(self, listener: Callable[[], Any]) -> None:
        """Subscribe a listener callback to state changes."""
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def unsubscribe(self, listener: Callable[[], Any]) -> None:
        """Unsubscribe a listener callback from state changes."""
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def notify(self) -> None:
        """Notify all change listeners."""
        for listener in list(self._change_listeners):
            with contextlib.suppress(Exception):
                result = listener()
                if inspect.isawaitable(result):
                    with contextlib.suppress(RuntimeError):
                        asyncio.get_running_loop().create_task(result)
                elif hasattr(result, "_fire"):
                    fire = result._fire()
                    if inspect.isawaitable(fire):
                        with contextlib.suppress(RuntimeError):
                            asyncio.get_running_loop().create_task(fire)

    def get_agent_service(self) -> AgentService:
        """Retrieve or initialize the active AgentService instance."""
        if self.agent_service is None:
            self.agent_service = AgentService(
                project_path=self.project_path,
                api_key=self.api_key,
            )
        return self.agent_service

    def get_autocomplete_service(self) -> AutocompleteService:
        """Retrieve or initialize the AutocompleteService for this session."""
        if self._autocomplete_service is None:
            skills = self.load_skills()
            mention_index = MentionIndex(self.project_path, skills=skills)
            command_registry = SlashCommandRegistry()
            self._autocomplete_service = AutocompleteService(
                mention_index, command_registry
            )
        return self._autocomplete_service

    def load_skills(self) -> list[SkillManifest]:
        """Load skill manifests from default discovery paths."""
        paths = get_default_skill_paths(DEFAULT_AGENT_NAME)
        loads, _diagnostics = load_skills_from_paths(paths)
        return [load.manifest for load in loads]

    @staticmethod
    def skill_info_from_manifest(manifest: SkillManifest) -> SkillInfo:
        """Convert a SkillManifest into the inspector-friendly SkillInfo shape."""
        return SkillInfo(
            name=manifest.name,
            description=manifest.description,
            scope=manifest.scope.value if manifest.scope else "",
            path=manifest.path,
        )

    def add_skill(self, manifest: SkillManifest) -> bool:
        """Add a skill to active_skills if not already present.

        Returns True when the skill was newly added (state changed).
        """
        info = self.skill_info_from_manifest(manifest)
        for existing in self.active_skills:
            if existing.name == info.name:
                return False
        self.active_skills.append(info)
        self.notify()
        return True

    def remove_skill(self, name: str) -> bool:
        """Remove a skill from active_skills by name.

        Returns True when a skill was actually removed.
        """
        for index, existing in enumerate(self.active_skills):
            if existing.name == name:
                del self.active_skills[index]
                self.notify()
                return True
        return False

    def clear_skills(self) -> None:
        """Remove all tracked skills."""
        if self.active_skills:
            self.active_skills.clear()
            self.notify()

    def add_attachment(self, name: str) -> None:
        """Add a file name to the pending attachments bound to next submission."""
        if name and name not in self.pending_attachments:
            self.pending_attachments.append(name)
            self.notify()

    def remove_attachment(self, index: int) -> None:
        """Remove a pending attachment by index (safe no-op if out of range)."""
        if 0 <= index < len(self.pending_attachments):
            del self.pending_attachments[index]
            self.notify()

    def add_mention(self, chip: MentionChip) -> None:
        """Add a mention chip to the current input."""
        self.selected_mentions.append(chip)
        self.notify()

    def remove_selected_mention(self, index: int) -> None:
        """Remove a selected mention chip by index."""
        if 0 <= index < len(self.selected_mentions):
            del self.selected_mentions[index]
            self.notify()

    def remove_last_mention(self) -> None:
        """Remove the most recently added mention chip."""
        if self.selected_mentions:
            self.selected_mentions.pop()
            self.notify()

    def clear_mentions(self) -> None:
        """Remove all mention chips."""
        if self.selected_mentions:
            self.selected_mentions.clear()
            self.notify()

    def clear_selected_mentions(self) -> None:
        """Remove all selected mention chips."""
        self.clear_mentions()

    def clear_attachments(self) -> None:
        """Remove all pending attachments."""
        if self.pending_attachments:
            self.pending_attachments.clear()
            self.notify()

    def add_background_task(
        self,
        task_id: str,
        name: str,
        *,
        parent_id: str | None = None,
        progress: float = 0.0,
    ) -> BackgroundTask:
        """Register a new background task (idempotent on duplicate id)."""
        existing = self.get_background_task(task_id)
        if existing is not None:
            return existing
        task = BackgroundTask(
            id=task_id,
            name=name,
            parent_id=parent_id,
            progress=progress,
        )
        self.background_tasks.append(task)
        self.notify()
        return task

    def update_background_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | str | None = None,
        progress: float | None = None,
        result: str | None = None,
        error: str | None = None,
    ) -> BackgroundTask | None:
        """Update fields on an existing background task (no-op if unknown)."""
        task = self.get_background_task(task_id)
        if task is None:
            return None
        if status is not None:
            task.status = TaskStatus(status)
        if progress is not None:
            task.progress = progress
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        if task.status in (TaskStatus.COMPLETE, TaskStatus.ERROR):
            task.ended_at = time.monotonic()
        self.notify()
        return task

    def remove_background_task(self, task_id: str) -> bool:
        """Remove a background task by id. Returns True if removed."""
        for i, task in enumerate(self.background_tasks):
            if task.id == task_id:
                del self.background_tasks[i]
                self.notify()
                return True
        return False

    def get_background_task(self, task_id: str) -> BackgroundTask | None:
        """Look up a background task by id."""
        for task in self.background_tasks:
            if task.id == task_id:
                return task
        return None

    def clear_background_tasks(self) -> None:
        """Remove all tracked background tasks."""
        if self.background_tasks:
            self.background_tasks.clear()
            self.notify()

    def toggle_inspector(self) -> None:
        """Toggle right context inspector visibility."""
        self.inspector_expanded = not self.inspector_expanded
        self.notify()

    def open_app_settings(self) -> None:
        """Open the Application Settings modal."""
        self._show_app_settings = True
        self._show_workspace_settings = False
        self.notify()

    def close_app_settings(self) -> None:
        """Close the Application Settings modal."""
        self._show_app_settings = False
        self.notify()

    def open_workspace_settings(self) -> None:
        """Open the Project Workspace Settings modal."""
        self._show_workspace_settings = True
        self._show_app_settings = False
        self.notify()

    def close_workspace_settings(self) -> None:
        """Close the Project Workspace Settings modal."""
        self._show_workspace_settings = False
        self.notify()

    @property
    def command_palette_open(self) -> bool:
        """Whether the command palette is visible."""
        return self._command_palette_open

    def set_command_palette_open(self, open: bool) -> None:
        """Set command palette visibility."""
        self._command_palette_open = open
        self.notify()

    def toggle_command_palette(self) -> None:
        """Toggle command palette visibility."""
        self._command_palette_open = not self._command_palette_open
        self.notify()

    def set_project(self, path: Path) -> None:
        """Change the active workspace project path."""
        self.project_path = path
        self.agent_service = None
        self._autocomplete_service = None
        self.clear_attachments()
        self.clear_mentions()
        self.add_recent_project(path)
        self.load_tomes()
        self.notify()

    def add_recent_project(self, path: Path) -> None:
        """Add or move a project path to the front of recent projects."""
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        if len(self.recent_projects) > 10:
            self.recent_projects = self.recent_projects[:10]
        self.notify()

    def new_conversation(self) -> None:
        """Reset conversation session to empty new state."""
        self.active_tome_id = None
        self.tome_title = "New Conversation"
        self.is_channeling = False
        self.messages = []
        self.total_mana_used = 0
        self.pending_attachments.clear()
        self.selected_mentions.clear()
        self.background_tasks.clear()
        self.clear_skills()
        self.load_tomes()

    def load_tomes(self) -> None:
        """Load and index all Tomes for the active project workspace."""
        self.loaded_tomes = self.tome_service.list_tomes_for_project(
            self.project_path, active_tome_id=self.active_tome_id
        )
        self.notify()

    def load_messages_for_tome(self, tome_id: str) -> None:
        """Load existing messages from a Tome's JSONL transcript."""
        ledger = self.tome_service.ledger
        try:
            entries = ledger.get_entries(tome_id)
        except ValueError, KeyError:
            self.messages = []
            return

        reconstructed: list[ChatMessage] = []
        for entry in entries:
            if entry.type in (TomeEntryType.MESSAGE, TomeEntryType.INVOCATION):
                payload = entry.payload
                role = str(payload.get("role", "assistant"))
                if role in ("user", "assistant"):
                    text, contemplation, parts = _extract_parts_and_content(
                        payload.get("content", "")
                    )
                    reconstructed.append(
                        ChatMessage(
                            role=role,
                            content=text,
                            contemplation=contemplation,
                            parts=parts,
                            model=payload.get("model"),
                        )
                    )
        self.messages = reconstructed
        self.notify()

    def switch_to_tome(self, tome_id: str) -> None:
        """Load a Tome session and switch the active conversation."""
        ledger = self.tome_service.ledger
        meta = ledger.open_tome(tome_id)
        if meta is None:
            return
        self.active_tome_id = meta.id
        self.tome_title = self.tome_service.get_tome_title(meta.id)
        self.is_channeling = False
        self.load_messages_for_tome(meta.id)
        self.load_tomes()

    def switch_model(self, model_id: str) -> None:
        """Switch the selected Realm model."""
        self.selected_model = model_id
        self.notify()

    def set_message_feedback(self, index: int, feedback: str | None) -> None:
        """Set or toggle feedback (thumbs up / thumbs down) on a message."""
        if 0 <= index < len(self.messages):
            msg = self.messages[index]
            if msg.feedback == feedback:
                msg.feedback = None
            else:
                msg.feedback = feedback
            self.notify()

    def submit_prompt(self, prompt: str) -> None:
        """Submit a new user prompt and start channeling Mvge response."""
        if self.is_channeling:
            return

        mention_text = " ".join(chip.text for chip in self.selected_mentions)
        text = prompt.strip()
        if not mention_text and not text:
            return

        if mention_text:
            text = f"{mention_text} {text}" if text else mention_text
        self.selected_mentions.clear()

        attachments = list(self.pending_attachments)
        self.pending_attachments.clear()
        user_msg = ChatMessage(role="user", content=text, attachments=attachments)
        self.messages.append(user_msg)

        # Append assistant response bubble
        assistant_msg = ChatMessage(
            role="assistant",
            model=self.selected_model,
            is_streaming=True,
        )
        self.messages.append(assistant_msg)
        self.is_channeling = True
        self.notify()

        # Start agent task
        service = self.get_agent_service()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "submit_prompt called without a running event loop — prompt dropped"
            )
            self.messages.pop()
            self.is_channeling = False
            self.notify()
            return
        if loop is not None:
            task = asyncio.ensure_future(service.run_prompt(text, self, assistant_msg))

            def _on_done(future: asyncio.Task[Any]) -> None:
                with contextlib.suppress(asyncio.CancelledError):
                    exc = future.exception()
                    if exc is not None:
                        assistant_msg.is_error = True
                        assistant_msg.error_message = str(exc)
                        assistant_msg.is_streaming = False
                        self.is_channeling = False
                        self.notify()

            task.add_done_callback(_on_done)
            self.active_task = task

    def stop_channeling(self) -> None:
        """Cancel and halt active agent channeling."""
        if self.active_task is not None:
            with contextlib.suppress(Exception):
                self.active_task.cancel()
        if self.agent_service is not None:
            self.agent_service.cancel()

        for msg in self.messages:
            if msg.is_streaming:
                msg.is_streaming = False

        self.is_channeling = False
        self.notify()

    def open_in_editor(self) -> None:
        """Spawn the default editor in the active project directory."""
        editor = os.environ.get("EDITOR", "code")
        with contextlib.suppress(FileNotFoundError):
            subprocess.Popen(
                [editor, str(self.project_path)],
                start_new_session=True,
            )

    def fork_tome(self) -> str | None:
        """Fork the active Tome and switch to the new branch."""
        if self.active_tome_id is None:
            return None
        ledger = self.tome_service.ledger
        leaf_id = ledger.get_leaf_id(self.active_tome_id)
        if leaf_id is None:
            return None
        forked = ledger.create_branched_tome(
            parent_tome_id=self.active_tome_id,
            cwd=str(self.project_path),
            fork_from_leaf_id=leaf_id,
        )
        self.switch_to_tome(forked.id)
        return forked.id

    def export_tome(self) -> Path | None:
        """Export the active Tome's JSONL transcript to the project directory."""
        if self.active_tome_id is None:
            return None
        src = self.tome_service.ledger.tome_file(self.active_tome_id)
        if not src.exists():
            return None
        dest = self.project_path / f"{self.active_tome_id[:8]}.jsonl"
        shutil.copy2(src, dest)
        return dest

    def clear_history(self) -> None:
        """Clear the current conversation history."""
        self.new_conversation()

    def refresh_changed_files(self) -> None:
        """Query git for changed files and update reactive state."""
        self.changed_files = get_changed_files(self.project_path)
        self.notify()

    def open_diff_review(self, path: str) -> None:
        """Open the Diff Review modal for the given file path."""
        self._selected_diff_path = path
        self.notify()

    def get_selected_diff_view(self) -> Any | None:
        """Return the DiffView for the currently selected diff file."""
        if not self._selected_diff_path:
            return None
        return get_diff_for_file(self.project_path, self._selected_diff_path)

    def clear_diff_selection(self) -> None:
        """Clear the selected diff path."""
        self._selected_diff_path = None
        self.notify()

    def add_artifact(self, artifact: Artifact) -> None:
        """Add an artifact to the session and notify listeners."""
        self.artifacts.append(artifact)
        self.notify()

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        """Look up an artifact by id."""
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None

    def open_artifact(self, artifact_id: str) -> None:
        """Select an artifact for preview in the drawer."""
        if self.get_artifact(artifact_id) is not None:
            self._selected_artifact_id = artifact_id
            self.notify()

    def close_artifact(self) -> None:
        """Clear the selected artifact preview."""
        self._selected_artifact_id = None
        self.notify()

    def get_selected_artifact(self) -> Artifact | None:
        """Return the currently selected artifact for preview."""
        if not self._selected_artifact_id:
            return None
        return self.get_artifact(self._selected_artifact_id)

    def set_current_view(self, view: str) -> None:
        """Switch the main content view."""
        self.current_view = view
        self.notify()

    def toggle_sidebar(self) -> None:
        """Toggle left sidebar visibility."""
        self.sidebar_open = not self.sidebar_open
        self.notify()

    def toggle_review(self) -> None:
        """Toggle right review rail visibility."""
        self.review_open = not self.review_open
        self.notify()

    def toggle_terminal(self) -> None:
        """Toggle terminal panel visibility."""
        self.terminal_open = not self.terminal_open
        self.notify()

    def set_pi_status(self, status: str) -> None:
        """Update the Mvge process status."""
        self.pi_status = status
        self.notify()

    def set_streaming(
        self, content: str, thinking: str = "", tool_calls: list | None = None
    ) -> None:
        """Update streaming state for the active assistant message."""
        self.is_streaming = True
        self.streaming_content = content
        self.streaming_thinking = thinking
        self.streaming_tool_calls = tool_calls or []
        self.notify()

    def clear_streaming(self) -> None:
        """Clear streaming state."""
        self.is_streaming = False
        self.streaming_content = ""
        self.streaming_thinking = ""
        self.streaming_tool_calls = []
        self.notify()

    def set_chat_side_panel(self, panel: str | None) -> None:
        """Set the active side panel in chat (files, diff, or None)."""
        self.chat_side_panel = panel
        self.notify()
