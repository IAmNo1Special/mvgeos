"""Pure-logic autocomplete engine for @-mention and /-slash-command popups.

This module contains no NiceGUI dependencies so it can be unit-tested in
isolation.  The rendering layer in ``input_dock.py`` wires these primitives
to the GUI.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pathspec
from mvgeos_runes.types import SkillManifest

ChangeListener = Callable[[], Any]


MENTION_FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyw",
        ".md",
        ".mdx",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".jsz",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".env",
        ".txt",
        ".sh",
        ".bash",
        ".zsh",
        ".css",
        ".scss",
        ".sass",
        ".html",
        ".sql",
        ".csv",
        ".svelte",
        ".vue",
        ".go",
        ".rs",
        ".rb",
        ".java",
        ".kt",
        ".swift",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".pl",
        ".php",
        ".r",
        ".scala",
        ".lua",
        ".vim",
        ".dockerfile",
        ".gitignore",
    }
)

SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".eggs",
        "build",
        "dist",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".idea",
        ".vscode",
        ".tox",
        "env",
    }
)

MAX_INDEXED_FILES = 1000


class MentionKind(StrEnum):
    """Category of an @-mention autocomplete result."""

    FILE = "file"
    SKILL = "skill"


class CommandKind(StrEnum):
    """Category of a slash-command autocomplete result."""

    SLASH = "slash"
    RUNE = "rune"


@dataclass
class MentionItem:
    """A single @-mention autocomplete candidate."""

    kind: MentionKind
    label: str
    value: str
    description: str = ""
    path: Path | None = None


@dataclass
class SlashCommandItem:
    """A single slash-command autocomplete candidate."""

    kind: CommandKind
    name: str
    description: str = ""
    value: str = ""


@dataclass
class MentionChip:
    """A selected autocomplete item rendered as a chip in the input field."""

    text: str
    kind: str
    icon: str = ""
    path: Path | None = None


def _score_query(key: str, query: str) -> tuple[int, int, int] | None:
    """Score a fuzzy subsequence match of *query* against *key*.

    Returns ``(start_pos, gap_count, key_len)`` — lower is better — or
    ``None`` when *query* is not a subsequence of *key*.
    """
    if not query:
        return (0, 0, len(key))
    key_lower = key.lower()
    idx = 0
    positions: list[int] = []
    for ch in query.lower():
        pos = key_lower.find(ch, idx)
        if pos == -1:
            return None
        positions.append(pos)
        idx = pos + 1
    start_pos = positions[0]
    gaps = sum(
        1 for i in range(1, len(positions)) if positions[i] > positions[i - 1] + 1
    )
    return (start_pos, gaps, len(key))


def fuzzy_filter(
    items: Sequence[object], query: str, key_attr: str = "label"
) -> list[object]:
    """Filter *items* using fuzzy subsequence matching on *key_attr*.

    When *query* is empty all *items* are returned unchanged.  Otherwise
    only items whose key contains every character of *query* in order are
    kept.  The result is sorted by match quality (earlier, more contiguous
    matches first) and then alphabetically by key.
    """
    if not query:
        return list(items)
    scored: list[tuple[tuple[int, int, int], object]] = []
    for item in items:
        key = getattr(item, key_attr, "")
        score = _score_query(key, query)
        if score is not None:
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], getattr(pair[1], key_attr, "").lower()))
    return [item for _, item in scored]


class SlashCommandRegistry:
    """Provides slash commands from CLI defaults and rune-registered commands."""

    CLI_SLASH_COMMANDS: dict[str, str] = {
        "/help": "Show available commands",
        "/quit": "Exit the session",
        "/exit": "Exit the session",
        "/model": "Switch or list models: /model [id] or /model --free",
        "/models": "List available models: /models [--free]",
        "/mode": "Toggle queue mode (all/one-at-a-time)",
        "/new": "Start a new session",
        "/session": "Show current session info",
        "/resume": "Resume a previous session: /resume <id>",
        "/spells": "List or set enabled spells: /spells [name, ...]",
        "/steer": "Steer agent mid-run: /steer <message>",
        "/followup": "Queue follow-up for post-run: /followup <message>",
        "/refresh-models": "Refresh model catalog from OpenRouter API",
    }

    def __init__(self, rune_commands: list[SlashCommandItem] | None = None) -> None:
        self._rune_commands = list(rune_commands or [])

    def get_commands(self) -> list[SlashCommandItem]:
        """Return all available slash commands (CLI + rune)."""
        items: list[SlashCommandItem] = []
        for name, desc in self.CLI_SLASH_COMMANDS.items():
            items.append(
                SlashCommandItem(
                    kind=CommandKind.SLASH,
                    name=name,
                    description=desc,
                    value=name,
                )
            )
        items.extend(self._rune_commands)
        return items

    @staticmethod
    def _filter_by_name(
        commands: list[SlashCommandItem], query: str
    ) -> list[SlashCommandItem]:
        """Filter commands by fuzzy match on name."""
        return cast(list[SlashCommandItem], fuzzy_filter(commands, query, "name"))


class MentionIndex:
    """Indexes workspace files and skills for @-mention autocomplete."""

    def __init__(
        self,
        project_path: Path,
        skills: list[SkillManifest] | None = None,
        max_files: int = MAX_INDEXED_FILES,
    ) -> None:
        self._project_path = project_path
        self._skills = skills or []
        self._max_files = max_files
        self._cache: list[MentionItem] | None = None
        self._gitignore_spec: pathspec.PathSpec[Any] | None = None
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        """Load .gitignore patterns from the project root."""
        gitignore_path = self._project_path / ".gitignore"
        if gitignore_path.exists():
            try:
                with open(gitignore_path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
                self._gitignore_spec = pathspec.PathSpec.from_lines("gitignore", lines)
            except Exception:
                # If parsing fails, ignore gitignore
                self._gitignore_spec = None
        else:
            self._gitignore_spec = None

    def _is_ignored(self, path: Path) -> bool:
        """Check if a path should be ignored based on .gitignore."""
        if self._gitignore_spec is None:
            return False
        try:
            rel = path.relative_to(self._project_path)
            return self._gitignore_spec.match_file(rel.as_posix())
        except ValueError:
            return False

    def index_files(self) -> list[MentionItem]:
        """Walk the project directory and return indexed file items."""
        items: list[MentionItem] = []
        if not self._project_path.exists():
            return items

        count = 0
        for root, dirs, files in os.walk(self._project_path):
            # Filter out ignored directories
            dirs[:] = [
                d
                for d in dirs
                if d not in SKIP_DIRS and not self._is_ignored(Path(root) / d)
            ]
            for fname in files:
                if count >= self._max_files:
                    return items
                ext = Path(fname).suffix
                if ext not in MENTION_FILE_EXTENSIONS:
                    continue
                fpath = Path(root) / fname
                if self._is_ignored(fpath):
                    continue
                try:
                    rel = fpath.relative_to(self._project_path)
                except ValueError:
                    continue
                items.append(
                    MentionItem(
                        kind=MentionKind.FILE,
                        label=rel.as_posix(),
                        value=rel.as_posix(),
                        path=fpath,
                    )
                )
                count += 1
        return items

    def index_skills(self) -> list[MentionItem]:
        """Return skill manifest items."""
        items: list[MentionItem] = []
        for skill in self._skills:
            items.append(
                MentionItem(
                    kind=MentionKind.SKILL,
                    label=skill.name,
                    value=f"@{skill.name}",
                    description=skill.description or "",
                )
            )
        return items

    def get_all_items(self) -> list[MentionItem]:
        """Return cached file + skill items (built on first call)."""
        if self._cache is None:
            self._cache = self.index_files() + self.index_skills()
        return list(self._cache)

    def search(self, query: str) -> list[MentionItem]:
        """Return fuzzy-filtered mention items."""
        return cast(
            list[MentionItem], fuzzy_filter(self.get_all_items(), query, "label")
        )

    def invalidate(self) -> None:
        """Clear the file/skill index cache."""
        self._cache = None


class AutocompleteMode(StrEnum):
    """Current autocomplete popup mode."""

    NONE = "none"
    MENTION = "mention"
    COMMAND = "command"


def get_last_word(text: str) -> tuple[str, int, int]:
    """Return ``(word, start, end)`` for the last whitespace-delimited word.

    If *text* is empty or ends with whitespace the current word is
    considered empty (``("", len(text), len(text))``).
    """
    if not text:
        return "", 0, 0
    last_idx = len(text) - 1
    if text[last_idx] in (" ", "\n", "\t", "\r"):
        return "", len(text), len(text)
    end = len(text)
    start = last_idx
    while start > 0 and text[start - 1] not in (" ", "\n", "\t", "\r"):
        start -= 1
    return text[start:end], start, end


def detect_trigger(
    text: str, cursor_pos: int | None = None
) -> tuple[AutocompleteMode, str] | None:
    """Detect an ``@`` or ``/`` mention/command trigger at the end of *text*.

    Returns ``(mode, query)`` when the last word starts with ``@`` or ``/``,
    otherwise ``None``.
    """
    if cursor_pos is not None:
        text = text[:cursor_pos]
    word, _, _ = get_last_word(text)
    if not word:
        return None
    first = word[0]
    if first == "@":
        return (AutocompleteMode.MENTION, word[1:])
    if first == "/":
        return (AutocompleteMode.COMMAND, word[1:])
    return None


@dataclass
class AutocompleteService:
    """Reactive controller for the autocomplete popup.

    Holds the current mode, query, filtered items, and selection index.
    The rendering layer calls :meth:`process_input` on each keystroke and
    queries the public attributes to decide what to render.
    """

    _mention_index: MentionIndex = field(repr=False)
    _command_registry: SlashCommandRegistry = field(repr=False)
    mode: AutocompleteMode = AutocompleteMode.NONE
    query: str = ""
    items: list[object] = field(default_factory=list)
    selected_index: int = 0
    is_open: bool = False
    _change_listeners: list[ChangeListener] = field(
        default_factory=list, repr=False, compare=False
    )
    _items_change_listeners: list[ChangeListener] = field(
        default_factory=list, repr=False, compare=False
    )

    def subscribe(self, listener: ChangeListener) -> None:
        """Subscribe a listener callback to autocomplete state changes."""
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def subscribe_items_changed(self, listener: ChangeListener) -> None:
        """Subscribe a listener to items list changes (open/close/query filter).
        This does NOT fire on selection index changes, only when the items
        list itself changes (open, close, query filter).
        """
        if listener not in self._items_change_listeners:
            self._items_change_listeners.append(listener)

    def _notify_listeners(self) -> None:
        """Notify all change listeners, swallowing exceptions."""
        for listener in self._change_listeners:
            with contextlib.suppress(Exception):
                listener()

    def _notify_items_changed(self) -> None:
        """Notify items change listeners (for popup re-render)."""
        for listener in self._items_change_listeners:
            with contextlib.suppress(Exception):
                listener()

    def process_input(self, text: str, cursor_pos: int | None = None) -> bool:
        """Update internal state from the textarea *text*.

        Returns ``True`` when the popup visibility or content changed.
        """
        result = detect_trigger(text, cursor_pos)
        if result is not None:
            mode, query = result
            if self.mode != mode or self.query != query or not self.is_open:
                self._open(mode, query)
                return True
            return False
        was_open = self.is_open
        self.close()
        return was_open

    def _open(self, mode: AutocompleteMode, query: str) -> None:
        self.mode = mode
        self.query = query
        self.is_open = True
        self.selected_index = 0
        self._refresh_items()
        self._notify_listeners()
        self._notify_items_changed()

    def _refresh_items(self) -> None:
        if self.mode == AutocompleteMode.MENTION:
            # @ triggers: only files (not skills)
            all_items = self._mention_index.search(self.query)
            self.items = cast(
                list[object], [i for i in all_items if i.kind == MentionKind.FILE]
            )
        elif self.mode == AutocompleteMode.COMMAND:
            # / triggers: slash commands + skills
            commands = cast(
                list[object],
                SlashCommandRegistry._filter_by_name(
                    self._command_registry.get_commands(), self.query
                ),
            )
            all_items = self._mention_index.search(self.query)
            skills = [i for i in all_items if i.kind == MentionKind.SKILL]
            self.items = commands + skills
        else:
            self.items = []

    def get_visible_items(self) -> list[object]:
        """Return the currently filtered items."""
        return list(self.items)

    def get_item_label(self, item: object) -> str:
        """Return the display label for an item."""
        if hasattr(item, "label"):
            return str(item.label)
        if hasattr(item, "name"):
            return str(item.name)
        return str(item)

    def get_item_description(self, item: object) -> str:
        """Return the description for an item."""
        if hasattr(item, "description"):
            return str(item.description or "")
        return ""

    def get_item_kind(self, item: object) -> str:
        """Return the kind string for an item."""
        if hasattr(item, "kind"):
            return str(item.kind)
        return ""

    def get_insertion_text(self, item: object) -> str:
        """Return the text to insert when *item* is selected."""
        if isinstance(item, MentionItem):
            if item.kind == MentionKind.FILE:
                return f"@{item.value}"
            if self.mode == AutocompleteMode.COMMAND:
                return f"/{item.label}"
            return item.value
        if isinstance(item, SlashCommandItem):
            return item.name
        return ""

    def create_chip(self, item: object) -> MentionChip | None:
        """Create a ``MentionChip`` from a selected autocomplete *item*."""
        text = self.get_insertion_text(item)
        if not text:
            return None
        kind_str = self.get_item_kind(item)
        icon = ""
        path = None
        if isinstance(item, MentionItem) and item.kind == MentionKind.FILE:
            icon = "insert_drive_file"
            path = item.path
        elif kind_str == MentionKind.SKILL:
            icon = "auto_awesome"
        elif kind_str == CommandKind.SLASH:
            icon = "slash"
        elif kind_str == CommandKind.RUNE:
            icon = "auto_awesome"
        return MentionChip(text=text, kind=kind_str, icon=icon, path=path)

    def get_word_range(
        self, text: str, cursor_pos: int | None = None
    ) -> tuple[int, int]:  # noqa: E501
        """Return ``(start, end)`` of the trigger word in *text*.

        Returns ``(-1, -1)`` when no trigger word is found.
        """
        if cursor_pos is not None:
            text = text[:cursor_pos]
        word, start, end = get_last_word(text)
        if not word:
            return -1, -1
        return start, end

    def select_current(self) -> str | None:
        """Return insertion text for the selected item and close the popup."""
        if (
            not self.items
            or self.selected_index < 0
            or self.selected_index >= len(self.items)
        ):
            return None
        item = self.items[self.selected_index]
        text = self.get_insertion_text(item)
        self.close()
        self._notify_listeners()
        return text

    def on_text_change(self, text: str, cursor_pos: int | None = None) -> bool:
        """Update autocomplete state on text change (alias for process_input)."""
        return self.process_input(text, cursor_pos)

    def get_selected_item(self) -> object | None:
        """Return the currently selected item or None."""
        if (
            not self.items
            or self.selected_index < 0
            or self.selected_index >= len(self.items)
        ):
            return None
        return self.items[self.selected_index]

    def select_next(self) -> None:
        """Move the selection cursor down by one (alias for move_down)."""
        self.move_down()

    def select_prev(self) -> None:
        """Move the selection cursor up by one (alias for move_up)."""
        self.move_up()

    def move_down(self) -> None:
        """Move the selection cursor down by one."""
        if self.items and self.selected_index < len(self.items) - 1:
            self.selected_index += 1
            self._notify_listeners()

    def move_up(self) -> None:
        """Move the selection cursor up by one."""
        if self.selected_index > 0:
            self.selected_index -= 1
            self._notify_listeners()

    def close(self) -> None:
        """Close the popup and reset selection state."""
        if not self.is_open:
            return
        self.is_open = False
        self.mode = AutocompleteMode.NONE
        self.query = ""
        self.items = []
        self.selected_index = 0
        self._notify_listeners()
        self._notify_items_changed()
