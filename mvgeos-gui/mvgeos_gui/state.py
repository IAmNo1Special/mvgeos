"""Application state management for mvgeos-gui."""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
        self.add_recent_project(path)
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
        self.notify()
