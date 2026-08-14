"""Application state management for mvgeos-gui."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mvgeos_tome.types import TomeEntryType

from mvgeos_gui.agent_service import AgentService
from mvgeos_gui.models import ChatMessage, extract_contemplation_tags
from mvgeos_gui.tome_service import TomeListEntry, TomeService


def _extract_text_and_contemplation(content: Any) -> tuple[str, str]:
    """Extract plain text and contemplation from message content."""
    if isinstance(content, str):
        return extract_contemplation_tags(content)
    if isinstance(content, list):
        text_parts: list[str] = []
        thought_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "contemplation":
                    thought_parts.append(str(item.get("text", "")))
                elif item_type == "text":
                    text_parts.append(str(item.get("text", "")))
                elif "text" in item:
                    text_parts.append(str(item["text"]))
            elif isinstance(item, str):
                text_parts.append(item)
        full_text = "\n".join(text_parts)
        cleaned, tag_thoughts = extract_contemplation_tags(full_text)
        if tag_thoughts:
            thought_parts.append(tag_thoughts)
        return cleaned, "\n\n".join(thought_parts).strip()
    return str(content or ""), ""


@dataclass
class AppState:
    """Reactive state container for MvgeOS desktop GUI session."""

    project_path: Path = field(default_factory=Path.cwd)
    active_tome_id: str | None = None
    tome_title: str = "New Conversation"
    sidebar_expanded: bool = True
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
    agent_service: AgentService | None = field(default=None, repr=False, compare=False)
    active_task: asyncio.Task[Any] | None = field(
        default=None, repr=False, compare=False
    )
    _change_listeners: list[Callable[[], Any]] = field(
        default_factory=list, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Initialize state invariants."""
        if not self.recent_projects and self.project_path:
            self.recent_projects.append(self.project_path)

    def subscribe(self, listener: Callable[[], Any]) -> None:
        """Subscribe a listener callback to state changes."""
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def notify(self) -> None:
        """Notify all change listeners."""
        for listener in self._change_listeners:
            with contextlib.suppress(Exception):
                listener()

    def get_agent_service(self) -> AgentService:
        """Retrieve or initialize the active AgentService instance."""
        if self.agent_service is None:
            self.agent_service = AgentService(
                project_path=self.project_path,
                api_key=self.api_key,
            )
        return self.agent_service

    def toggle_sidebar(self) -> None:
        """Toggle left navigation sidebar visibility."""
        self.sidebar_expanded = not self.sidebar_expanded
        self.notify()

    def toggle_inspector(self) -> None:
        """Toggle right context inspector visibility."""
        self.inspector_expanded = not self.inspector_expanded
        self.notify()

    def set_project(self, path: Path) -> None:
        """Change the active workspace project path."""
        self.project_path = path
        self.agent_service = None
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
                    text, contemplation = _extract_text_and_contemplation(
                        payload.get("content", "")
                    )
                    reconstructed.append(
                        ChatMessage(
                            role=role,
                            content=text,
                            contemplation=contemplation,
                            model=payload.get("model"),
                        )
                    )
        self.messages = reconstructed

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
        text = prompt.strip()
        if not text or self.is_channeling:
            return

        # Append user message bubble
        user_msg = ChatMessage(role="user", content=text)
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
        with contextlib.suppress(RuntimeError):
            self.active_task = asyncio.create_task(
                service.run_prompt(text, self, assistant_msg)
            )

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
