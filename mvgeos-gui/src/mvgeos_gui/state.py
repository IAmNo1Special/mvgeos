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
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from mvgeos_agent import (
    fetch_marketplace_mvges,
    install_mvge,
    list_installed_mvges,
    uninstall_mvge,
)
from mvgeos_provider import (
    get_default_realm_registry,
    get_model_options,
    get_models_for_provider,
    get_providers_for_realm,
    get_supported_contemplation_levels,
    is_realm_router,
)
from mvgeos_runes import (
    fetch_marketplace_runes,
    install_rune,
    install_skill,
    list_installed_runes,
    set_rune_enabled,
    uninstall_rune,
)
from mvgeos_runes.types import SkillManifest
from mvgeos_tome.types import TomeEntry, TomeEntryType, TomeVersionError

from mvgeos_gui.autocomplete import (
    AutocompleteService,
    MentionChip,
    MentionIndex,
    SlashCommandRegistry,
)
from mvgeos_gui.git_workspace import ChangedFile, get_changed_files, get_diff_for_file
from mvgeos_gui.models import (
    Artifact,
    BackgroundTask,
    ChatMessage,
    SkillInfo,
    TaskStatus,
    User,
)
from mvgeos_gui.services.agent_service import AgentService
from mvgeos_gui.services.auth_service import AuthService
from mvgeos_gui.services.config_service import ConfigService
from mvgeos_gui.services.tome_service import TomeListEntry, TomeService
from mvgeos_gui.transcript import InvocationTranscript

logger = logging.getLogger(__name__)


def format_channeling_elapsed(seconds: float) -> str:
    """Format an elapsed channeling duration compactly ("45s", "2m 05s")."""
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    return f"{total // 60}m {total % 60:02d}s"


@dataclass
class AppState:
    """Reactive state container for MvgeOS desktop GUI session."""

    project_path: Path = field(default_factory=Path.cwd)
    active_tome_id: str | None = None
    tome_title: str = "New Conversation"
    inspector_expanded: bool = True
    selected_realm: str = "openrouter"
    selected_provider: str | None = "nvidia"
    selected_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    contemplation_level: str = "medium"
    recent_projects: list[Path] = field(default_factory=list)
    is_channeling: bool = False
    channeling_started_at: float | None = None
    tome_service: TomeService = field(
        default_factory=TomeService, repr=False, compare=False
    )
    loaded_tomes: list[TomeListEntry] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)
    total_mana_used: int = 0
    # Latest provider-reported token usage for the context gauge. Distinct
    # from cumulative Mana: these are raw token counts off the last provider
    # response (input + output). None until a response reports real usage.
    context_input_tokens: int | None = None
    context_output_tokens: int | None = None
    active_prompt: str = ""
    # Draft text typed into the composer. The composer re-renders when it moves
    # between the centered empty-state slot and the bottom dock; the draft
    # restores the textarea so unsent text survives the move.
    composer_draft: str = ""
    # Plan mode: the engine only offers spells marked read_only. Toggled from
    # the chat toolbar or the command palette.
    plan_mode: bool = False
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
    _streaming_listeners: list[Callable[[], Any]] = field(
        default_factory=list, repr=False, compare=False
    )
    _view_listeners: dict[str, list[Callable[[], Any]]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _streaming_view_listeners: dict[str, list[Callable[[], Any]]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _selected_diff_path: str | None = field(default=None, repr=False, compare=False)
    changed_files: list[ChangedFile] = field(default_factory=list)
    _selected_artifact_id: str | None = field(default=None, repr=False, compare=False)
    artifacts: list[Artifact] = field(default_factory=list)
    _config_service: ConfigService = field(
        default_factory=ConfigService, repr=False, compare=False
    )
    _show_app_settings: bool = False
    _show_rename_dialog: bool = False
    _show_workspace_settings: bool = False
    _show_login: bool = False
    _auth_service: AuthService = field(
        default_factory=AuthService, repr=False, compare=False
    )
    current_user: User | None = field(default=None, repr=False, compare=False)
    current_view: str = "chat"
    sidebar_open: bool = True
    review_open: bool = False
    mvge_status: str = "idle"
    chat_side_panel: str | None = None
    _sidebar_width: int = 260
    _review_width: int = 320
    _command_palette_open: bool = False
    _expanded_cards: set[str] = field(default_factory=set, repr=False, compare=False)
    _collapsed_cards: set[str] = field(default_factory=set, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize state invariants."""
        if not self.recent_projects and self.project_path:
            self.recent_projects.append(self.project_path)
        if "/" in self.selected_model and self.selected_provider == "nvidia":
            prefix = self.selected_model.split("/")[0]
            self.selected_provider = prefix

    def subscribe(self, listener: Callable[[], Any]) -> None:
        """Subscribe a listener callback to state changes."""
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def unsubscribe(self, listener: Callable[[], Any]) -> None:
        """Unsubscribe a listener callback from state changes."""
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def clear_listeners(self) -> None:
        """Clear all registered change listeners."""
        self._change_listeners.clear()

    def notify(self) -> None:
        """Notify all change listeners."""
        for listener in list(self._change_listeners):
            with contextlib.suppress(Exception):
                result = listener()
                if inspect.iscoroutine(result):
                    coro = cast(Coroutine[Any, Any, None], result)
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(coro)
                    except RuntimeError:
                        coro.close()

    def subscribe_streaming(self, listener: Callable[[], Any]) -> None:
        """Subscribe a listener callback to streaming token updates."""
        if listener not in self._streaming_listeners:
            self._streaming_listeners.append(listener)

    def unsubscribe_streaming(self, listener: Callable[[], Any]) -> None:
        """Unsubscribe a listener callback from streaming token updates."""
        if listener in self._streaming_listeners:
            self._streaming_listeners.remove(listener)

    def subscribe_view(self, key: str, listener: Callable[[], Any]) -> None:
        """Subscribe a view-scoped listener tracked under *key*.

        View listeners render a specific panel; they are dropped via
        :meth:`clear_view_listeners` when the panel re-renders so stale
        refreshables on deleted elements never accumulate.
        """
        tracked = self._view_listeners.setdefault(key, [])
        if listener not in tracked:
            tracked.append(listener)
        self.subscribe(listener)

    def subscribe_streaming_view(self, key: str, listener: Callable[[], Any]) -> None:
        """Subscribe a streaming view-scoped listener tracked under *key*."""
        tracked = self._streaming_view_listeners.setdefault(key, [])
        if listener not in tracked:
            tracked.append(listener)
        self.subscribe_streaming(listener)

    def clear_view_listeners(self, key: str) -> None:
        """Detach all view-scoped listeners tracked under *key*."""
        for listener in self._view_listeners.pop(key, []):
            self.unsubscribe(listener)
        for listener in self._streaming_view_listeners.pop(key, []):
            self.unsubscribe_streaming(listener)

    def clear_all_view_listeners(self) -> None:
        """Detach every view-scoped listener from all keys.

        Call at the top of a panel render: the previous render pass owned
        the tracked listeners, and its elements are about to be replaced.
        """
        for key in list(self._view_listeners):
            self.clear_view_listeners(key)
        for key in list(self._streaming_view_listeners):
            self.clear_view_listeners(key)
        autocomplete = self._autocomplete_service
        if autocomplete is not None:
            autocomplete.clear_items_changed_listeners()

    def view_listener_count(self, key: str | None = None) -> int:
        """Return the number of tracked view-scoped listeners."""
        if key is not None:
            return len(self._view_listeners.get(key, [])) + len(
                self._streaming_view_listeners.get(key, [])
            )
        total = sum(len(v) for v in self._view_listeners.values())
        total += sum(len(v) for v in self._streaming_view_listeners.values())
        autocomplete = self._autocomplete_service
        if autocomplete is not None:
            total += autocomplete.items_changed_listener_count
        return total

    def notify_streaming(self) -> None:
        """Notify streaming listeners of rapid token updates.

        If streaming listeners are registered (e.g. active streaming bubble),
        notify only them to prevent whole-thread DOM re-renders. If no streaming
        listeners are registered (e.g. headless tests), fall back to general
        change listeners.
        """
        targets = (
            self._streaming_listeners
            if self._streaming_listeners
            else self._change_listeners
        )
        for listener in list(targets):
            with contextlib.suppress(Exception):
                result = listener()
                if inspect.iscoroutine(result):
                    coro = cast(Coroutine[Any, Any, None], result)
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(coro)
                    except RuntimeError:
                        coro.close()

    def get_agent_service(self) -> AgentService:
        """Retrieve or initialize the active AgentService instance."""
        if self.agent_service is None:
            self.agent_service = AgentService(
                project_path=self.project_path,
                api_key=self.api_key,
            )
        return self.agent_service

    def reset_agent(self) -> None:
        """Reset the cached agent in AgentService if one exists."""
        if self.agent_service is not None:
            self.agent_service.reset_agent()

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
        """Load skill manifests from project and user skill directories."""
        skills: list[SkillManifest] = []
        search_dirs = [
            self.project_path / ".agents" / "skills",
            Path("~/.agents/skills").expanduser(),
        ]
        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for item in sorted(sdir.iterdir()):
                if item.is_dir() and (item / "SKILL.md").is_file():
                    skills.append(
                        SkillManifest(
                            name=item.name,
                            description=f"Skill {item.name}",
                            path=str(item),
                        )
                    )
        return skills

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

    def get_background_task(self, task_id: str) -> BackgroundTask | None:
        """Look up a background task by id."""
        for task in self.background_tasks:
            if task.id == task_id:
                return task
        return None

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

    def open_rename_dialog(self) -> None:
        """Open the Rename session dialog."""
        self._show_rename_dialog = True
        self.notify()

    def close_rename_dialog(self) -> None:
        """Close the Rename session dialog."""
        self._show_rename_dialog = False
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
        self.channeling_started_at = None
        self.messages = []
        self.total_mana_used = 0
        self.reset_context_usage()
        self.pending_attachments.clear()
        self.selected_mentions.clear()
        self.background_tasks.clear()
        self.clear_skills()
        # Drop the cached agent: it is bound to the old tome and would
        # otherwise resume it on the next send instead of starting fresh.
        self.reset_agent()
        self.load_tomes()

    def record_context_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Record the latest provider-reported token usage for the gauge."""
        self.context_input_tokens = input_tokens
        self.context_output_tokens = output_tokens
        self.notify()

    def reset_context_usage(self) -> None:
        """Clear recorded token usage; the gauge hides until new usage arrives."""
        self.context_input_tokens = None
        self.context_output_tokens = None

    def get_verified_context_window(self) -> int | None:
        """Return the selected model's context window, or None if unverified.

        Only a registry entry with a real context window counts. The registry
        silently substitutes 4096 when an entry has no ``context_length``
        (see model_registry.py), so exactly 4096 is treated as "unknown"
        rather than displayed as fact.
        """
        try:
            reg = get_default_realm_registry()
            model = reg.model_registry.get(self.selected_model)
        except Exception:
            return None
        if model is None:
            return None
        if model.context_window <= 0 or model.context_window == 4096:
            return None
        return model.context_window

    def load_tomes(self) -> None:
        """Load and index all Tomes for the active project workspace."""
        self.loaded_tomes = self.tome_service.list_tomes_for_project(
            self.project_path, active_tome_id=self.active_tome_id
        )
        self.notify()

    def load_messages_for_tome(self, tome_id: str) -> None:
        """Load existing messages from a Tome's JSONL transcript."""
        try:
            entries = self.tome_service.factory.get_entries(tome_id)
        except (FileNotFoundError, TomeVersionError, ValueError, KeyError):
            self.messages = []
            return

        reconstructed: list[ChatMessage] = []
        for entry in entries:
            if entry.type == TomeEntryType.MESSAGE:
                payload = entry.payload
                role = str(payload.get("role", "assistant"))
                if role in ("user", "assistant"):
                    transcript = InvocationTranscript.from_tome_content(
                        payload.get("content", ""),
                        role=role,
                        model=payload.get("model"),
                    )
                    reconstructed.append(transcript.message)
        self.messages = reconstructed
        self.notify()

    def switch_to_tome(self, tome_id: str) -> None:
        """Load a Tome session and switch the active conversation."""
        try:
            meta = self.tome_service.factory.open_tome(tome_id)
        except TomeVersionError:
            return
        if meta is None:
            return
        self.active_tome_id = meta.id
        self.tome_title = self.tome_service.get_tome_title(meta.id)
        self.is_channeling = False
        self.channeling_started_at = None
        self.reset_context_usage()
        # Drop the cached agent: it is bound to the previous tome and would
        # otherwise keep running against the wrong session.
        self.reset_agent()
        self.load_messages_for_tome(meta.id)
        self.load_tomes()

    def get_realms(self) -> list[str]:
        """Return available realm identifiers."""
        try:
            reg = get_default_realm_registry()
            realms = ["openrouter"]
            for r in reg.get_registered_realm_factories():
                if r not in realms:
                    realms.append(r)
            return realms
        except Exception:
            return ["openrouter"]

    def is_router_realm(self, realm: str | None = None) -> bool:
        """Return True if the realm is a router requiring provider selection."""
        target_realm = realm or self.selected_realm
        try:
            return is_realm_router(target_realm)
        except Exception:
            return target_realm.lower() == "openrouter"

    def get_providers_for_selected_realm(self) -> list[str]:
        """Return list of providers available for the current realm."""
        if not self.is_router_realm(self.selected_realm):
            return []
        try:
            providers = get_providers_for_realm(self.selected_realm)
            if not providers and self.selected_realm == "openrouter":
                providers = [
                    "anthropic",
                    "google",
                    "meta-llama",
                    "mistralai",
                    "nvidia",
                    "openai",
                    "qwen",
                ]
            return providers
        except Exception:
            return ["nvidia"]

    def get_models_for_selection(self) -> list[str]:
        """Return model IDs matching the current realm and provider selection."""
        try:
            if self.is_router_realm(self.selected_realm):
                if self.selected_provider:
                    models = get_models_for_provider(
                        self.selected_provider, self.selected_realm
                    )
                    if models:
                        return [m.id for m in models]
                    return [self.selected_model]
            else:
                reg = get_default_realm_registry()
                all_models = reg.model_registry.list_all()
                matching = [
                    m.id
                    for m in all_models
                    if (
                        m.realm == self.selected_realm
                        or m.provider_prefix == self.selected_realm
                    )
                ]
                if matching:
                    return matching
                return [f"{self.selected_realm}/default"]
        except Exception:
            pass
        return [self.selected_model]

    def get_model_options_for_selection(self) -> dict[str, str]:
        """Return dict of model IDs to display names for current selection.

        For router realms, repeated provider prefixes followed by ': ' are stripped.
        Direct providers retain their model names without modification.
        """
        all_options = get_model_options()
        model_ids = self.get_models_for_selection()
        model_options = {mid: all_options.get(mid, mid) for mid in model_ids}
        if self.selected_model not in model_options:
            model_options[self.selected_model] = all_options.get(
                self.selected_model, self.selected_model
            )
        if self.is_router_realm(self.selected_realm):
            model_options = {
                mid: (name.split(": ", 1)[1] if ": " in name else name)
                for mid, name in model_options.items()
            }
        return model_options

    def get_contemplation_levels_for_selected_model(self) -> list[str]:
        """Return contemplation levels supported by the selected model."""
        try:
            levels = get_supported_contemplation_levels(self.selected_model)
            if levels:
                return levels
            reg = get_default_realm_registry()
            model = reg.model_registry.get(self.selected_model)
            if model is not None:
                if model.supported_contemplation_levels:
                    return list(model.supported_contemplation_levels)
                if model.supports_contemplation:
                    return ["none", "low", "medium", "high", "x-high"]
        except Exception:
            pass
        return []

    def supports_contemplation_for_selected_model(self) -> bool:
        """Return True if the selected model supports contemplation / reasoning."""
        levels = self.get_contemplation_levels_for_selected_model()
        if levels:
            return True
        try:
            reg = get_default_realm_registry()
            model = reg.model_registry.get(self.selected_model)
            return bool(model.supports_contemplation) if model is not None else False
        except Exception:
            return False

    def _cascade_contemplation(self) -> None:
        """Ensure contemplation level matches supported levels if any."""
        if self.supports_contemplation_for_selected_model():
            levels = self.get_contemplation_levels_for_selected_model()
            if levels and self.contemplation_level not in levels:
                self.contemplation_level = "medium" if "medium" in levels else levels[0]

    def switch_realm(self, realm: str) -> None:
        """Switch realm and cascade provider, model, and contemplation."""
        self.selected_realm = realm
        if self.is_router_realm(realm):
            providers = self.get_providers_for_selected_realm()
            if not self.selected_provider or self.selected_provider not in providers:
                self.selected_provider = providers[0] if providers else None
        else:
            self.selected_provider = None

        models = self.get_models_for_selection()
        if self.selected_model not in models:
            self.selected_model = models[0] if models else self.selected_model

        self._cascade_contemplation()
        self.notify()

    def switch_provider(self, provider: str | None) -> None:
        """Switch provider and cascade model and contemplation."""
        self.selected_provider = provider
        models = self.get_models_for_selection()
        if self.selected_model not in models:
            self.selected_model = models[0] if models else self.selected_model

        self._cascade_contemplation()
        self.notify()

    def switch_model(self, model_id: str) -> None:
        """Switch the selected Realm model and cascade contemplation."""
        self.selected_model = model_id
        if "/" in model_id and self.is_router_realm(self.selected_realm):
            prefix = model_id.split("/")[0]
            providers = self.get_providers_for_selected_realm()
            if prefix in providers:
                self.selected_provider = prefix

        self._cascade_contemplation()
        self.notify()

    def set_contemplation_level(self, level: str) -> None:
        """Set contemplation level for the active session."""
        self.contemplation_level = level
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
        user_msg = InvocationTranscript.for_summoner(text, attachments)
        self.messages.append(user_msg)

        # Append assistant response bubble
        assistant_msg = ChatMessage(
            role="assistant",
            model=self.selected_model,
            is_streaming=True,
        )
        self.messages.append(assistant_msg)
        self.is_channeling = True
        self.channeling_started_at = time.monotonic()
        self.mvge_status = "channeling"
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
            self.channeling_started_at = None
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
                        self.channeling_started_at = None
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
        self.channeling_started_at = None
        self.notify()

    def elapsed_channeling_seconds(self) -> float | None:
        """Seconds since channeling started, or None when not channeling."""
        if not self.is_channeling or self.channeling_started_at is None:
            return None
        return max(0.0, time.monotonic() - self.channeling_started_at)

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
        parent_title = self.tome_service.get_tome_title(self.active_tome_id)
        factory = self.tome_service.factory
        leaf_id = factory.get_leaf_id(self.active_tome_id)
        if leaf_id is None:
            return None
        forked = factory.create_branched_tome(
            parent_tome_id=self.active_tome_id,
            cwd=str(self.project_path),
            fork_from_leaf_id=leaf_id,
        )
        self.switch_to_tome(forked.tome_id)
        # The engine fork copies the message chain up to the leaf, which
        # drops the parent_id-less TOME_INFO title entry. Re-apply the
        # parent's title so the branch keeps its name.
        if self.tome_title != parent_title:
            self.rename_tome(parent_title)
        return forked.tome_id

    def export_tome(self) -> Path | None:
        """Export the active Tome's JSONL transcript to the project directory."""
        if self.active_tome_id is None:
            return None
        src = self.tome_service.factory.tome_file(self.active_tome_id)
        if not src.exists():
            return None
        dest = self.project_path / f"{self.active_tome_id[:8]}.jsonl"
        shutil.copy2(src, dest)
        return dest

    def rename_tome(self, new_title: str) -> bool:
        """Rename the active Tome by appending a TOME_INFO title entry.

        get_tome_title() reads entries newest-first, so the latest rename
        always wins. Returns False when there is no active Tome, the title
        is blank, or the Tome file cannot be written.
        """
        title = new_title.strip()
        if self.active_tome_id is None or not title:
            return False
        entry = TomeEntry(
            id=uuid.uuid4().hex[:12],
            parent_id=None,
            type=TomeEntryType.TOME_INFO,
            timestamp=time.time(),
            payload={"title": title},
        )
        try:
            self.tome_service.factory.open_write(self.active_tome_id).append(entry)
        except (FileNotFoundError, ValueError, RuntimeError):
            return False
        self.tome_title = title
        self.load_tomes()
        return True

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
        """Toggle left sidebar collapsed state."""
        try:
            from nicegui import app as nicegui_app

            nicegui_app.storage.user[
                "sidebar-collapsed"
            ] = not nicegui_app.storage.user.get("sidebar-collapsed", False)
            self.sidebar_open = not nicegui_app.storage.user["sidebar-collapsed"]
        except Exception:
            self.sidebar_open = not self.sidebar_open
        self.notify()

    def toggle_review(self) -> None:
        """Toggle right review rail visibility."""
        self.review_open = not self.review_open
        self.notify()

    def set_plan_mode(self, enabled: bool) -> list[str]:
        """Enable or disable plan mode (read-only spells only).

        Drives the engine agent's plan-mode filter, then mirrors the flag
        locally. Returns the spell names still active after the toggle so
        callers can warn when plan mode leaves the agent without tools.
        """
        service = self.get_agent_service()
        agent = service.get_or_create_agent(self)
        agent.set_plan_mode(enabled)
        self.plan_mode = enabled
        self.notify()
        return list(agent.enabled_spells)

    def toggle_plan_mode(self) -> list[str]:
        """Flip plan mode. Returns the spell names active after the toggle."""
        return self.set_plan_mode(not self.plan_mode)

    def show_login(self) -> None:
        """Open the login dialog."""
        self._show_login = True
        self.notify()

    def hide_login(self) -> None:
        """Close the login dialog."""
        self._show_login = False
        self.notify()

    def set_mvge_status(self, status: str) -> None:
        """Update the Mvge activity status (idle, channeling, working)."""
        self.mvge_status = status
        self.notify()

    def set_chat_side_panel(self, panel: str | None) -> None:
        """Set the active side panel in chat (files, diff, or None)."""
        self.chat_side_panel = panel
        self.notify()

    def is_card_expanded(self, card_id: str, default: bool = False) -> bool:
        """Check whether a card/expansion is currently expanded."""
        if card_id in self._expanded_cards:
            return True
        if card_id in self._collapsed_cards:
            return False
        return default

    def set_card_expansion(self, card_id: str, expanded: bool) -> None:
        """Record expansion state without triggering notification re-renders."""
        if expanded:
            self._expanded_cards.add(card_id)
            self._collapsed_cards.discard(card_id)
        else:
            self._collapsed_cards.add(card_id)
            self._expanded_cards.discard(card_id)

    def is_rune_installed(self, rune_name: str) -> bool:
        """Check if a rune extension is installed in ~/.agents/extensions."""
        target = Path("~/.agents/extensions").expanduser() / rune_name
        return target.is_dir()

    async def fetch_marketplace_runes_async(self) -> dict[str, Any]:
        """Fetch available marketplace runes asynchronously."""
        return await asyncio.to_thread(fetch_marketplace_runes)

    async def list_installed_runes_async(self) -> list[dict[str, Any]]:
        """List installed runes asynchronously."""
        return await asyncio.to_thread(list_installed_runes)

    async def install_rune_async(self, source: str) -> bool:
        """Install a rune from marketplace, git, or path asynchronously."""
        try:
            await asyncio.to_thread(install_rune, source)
            if self.agent_service and self.agent_service._agent:
                load_runes = getattr(self.agent_service._agent, "_load_runes", None)
                if callable(load_runes):
                    res = load_runes()
                    if inspect.isawaitable(res):
                        await res
            self.notify()
            return True
        except Exception as exc:
            logger.warning("Failed to install rune '%s': %s", source, exc)
            return False

    async def uninstall_rune_async(self, rune_name: str) -> bool:
        """Uninstall a rune and unregister its realm factory if registered."""
        result = bool(await asyncio.to_thread(uninstall_rune, rune_name))
        get_default_realm_registry().unregister_realm_factory(rune_name)
        self.notify()
        return result

    async def set_rune_enabled_async(self, rune_name: str, enabled: bool) -> bool:
        """Enable or disable an installed rune by updating its manifest."""
        result = bool(await asyncio.to_thread(set_rune_enabled, rune_name, enabled))
        self.notify()
        return result

    async def install_skill_async(
        self, source: str, name: str | None = None
    ) -> str | None:
        """Install a skill from a local path or git URL.

        Returns the installed skill name on success, None on failure.
        """
        try:
            dest = await asyncio.to_thread(install_skill, source, name)
            self.notify()
            return dest.name
        except Exception as exc:
            logger.warning("Failed to install skill from '%s': %s", source, exc)
            return None

    def is_mvge_installed(self, mvge_name: str) -> bool:
        """Check if an mvge agent is installed in ~/.agents/agents."""
        normalized = mvge_name.replace("-", "_")
        target = Path("~/.agents/agents").expanduser() / normalized
        return target.is_dir()

    async def fetch_marketplace_mvges_async(self) -> dict[str, Any]:
        """Fetch available marketplace mvges asynchronously."""
        return await asyncio.to_thread(fetch_marketplace_mvges)

    async def list_installed_mvges_async(self) -> list[dict[str, Any]]:
        """List installed mvges asynchronously."""
        return await asyncio.to_thread(list_installed_mvges)

    async def install_mvge_async(self, source: str) -> bool:
        """Install an mvge from marketplace, git, or path asynchronously."""
        try:
            await asyncio.to_thread(install_mvge, source)
            self.notify()
            return True
        except Exception as exc:
            logger.warning("Failed to install mvge '%s': %s", source, exc)
            return False

    async def uninstall_mvge_async(self, mvge_name: str) -> bool:
        """Uninstall an mvge asynchronously."""
        try:
            result = bool(await asyncio.to_thread(uninstall_mvge, mvge_name))
            self.notify()
            return result
        except Exception as exc:
            logger.warning("Failed to uninstall mvge '%s': %s", mvge_name, exc)
            return False
