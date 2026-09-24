"""Pure-logic autocomplete engine for @-mention and /-slash-command popups.

This module contains no NiceGUI dependencies so it can be unit-tested in
isolation.  The rendering layer in ``input_dock.py`` wires these primitives
to the GUI.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pathspec
from mvgeos_agent.commands import SLASH_COMMANDS
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


def _single_leading_slash(name: str) -> str:
    """Return *name* with exactly one leading slash.

    Command sources disagree on the convention — CLI keys carry the slash,
    rune manifests declare bare names — so normalize at every boundary
    rather than trusting the input. Autocomplete must never produce
    ``//command``.
    """
    return "/" + name.lstrip("/")


class SlashCommandRegistry:
    """Provides slash commands from CLI defaults and rune-registered commands."""

    CLI_SLASH_COMMANDS: dict[str, str] = dict(SLASH_COMMANDS)

    def __init__(self, rune_commands: list[SlashCommandItem] | None = None) -> None:
        self._rune_commands = [
            SlashCommandItem(
                kind=item.kind,
                name=_single_leading_slash(item.name),
                description=item.description,
                value=_single_leading_slash(item.value),
            )
            for item in (rune_commands or [])
        ]

    def get_commands(self) -> list[SlashCommandItem]:
        """Return all available slash commands (CLI + rune)."""
        items: list[SlashCommandItem] = []
        for name, desc in self.CLI_SLASH_COMMANDS.items():
            clean = _single_leading_slash(name)
            items.append(
                SlashCommandItem(
                    kind=CommandKind.SLASH,
                    name=clean,
                    description=desc,
                    value=clean,
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
        self._signature: tuple[tuple[tuple[str, float, str], ...], int] | None = None
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
        """Return cached file + skill items, rebuilding when the tree changed.

        The index rebuilds lazily on query: a cheap directory-mtime
        signature of the project tree is compared on every call, so files
        added, removed, or renamed after startup appear in @ completions
        without a restart and without a background file watcher.
        """
        signature = self._tree_signature()
        if self._cache is None or signature != self._signature:
            # The .gitignore itself may have changed: reload before
            # reindexing so new ignore rules apply immediately.
            self._load_gitignore()
            self._cache = self.index_files() + self.index_skills()
            self._signature = signature
        return list(self._cache)

    @staticmethod
    def _hash_entry_names(entries: list[os.DirEntry[str]]) -> str:
        """Hash the sorted immediate entry names of a directory.

        Windows does not update a directory's ``st_mtime`` on a
        same-directory rename (it updates LastChangeTime, which
        ``os.stat`` does not expose), so mtime alone misses renames.
        Including entry names makes the signature change on
        add/remove/rename on every platform.
        """
        hasher = hashlib.sha256()
        for name in sorted(entry.name for entry in entries):
            hasher.update(name.encode("utf-8", "surrogatepass"))
            hasher.update(b"\x00")
        return hasher.hexdigest()

    def _tree_signature(self) -> tuple[tuple[tuple[str, float, str], ...], int] | None:
        """Cheap staleness signature of the indexed directory tree.

        Records ``(relative dir path, mtime, entry-names hash)`` for every
        indexed directory plus the project ``.gitignore`` file, and the total
        file count as a backstop for filesystems with coarse mtime
        granularity. A directory's mtime changes when entries are added or
        removed inside it, but on Windows a same-directory rename does not
        update ``st_mtime``; the entry-names hash covers renames (and
        add/remove) on every platform. File *content* edits are
        intentionally ignored: the index only cares about paths. Returns
        None when the project directory does not exist.
        """
        if not self._project_path.is_dir():
            return None
        dirs: list[tuple[str, float, str]] = []
        file_count = 0
        gitignore = self._project_path / ".gitignore"
        if gitignore.is_file():
            with contextlib.suppress(OSError):
                dirs.append((".gitignore", gitignore.stat().st_mtime, ""))
        stack = [self._project_path]
        while stack:
            current = stack.pop()
            try:
                current_mtime = current.stat().st_mtime
            except OSError:
                continue
            try:
                rel = current.relative_to(self._project_path).as_posix()
            except ValueError:
                continue
            try:
                with os.scandir(current) as it:
                    entries = list(it)
            except OSError:
                entries = []
            dirs.append((rel, current_mtime, self._hash_entry_names(entries)))
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in SKIP_DIRS:
                            continue
                        if self._is_ignored(Path(entry.path)):
                            continue
                        stack.append(Path(entry.path))
                    else:
                        file_count += 1
                except OSError:
                    continue
        dirs.sort()
        return (tuple(dirs), file_count)

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

    def unsubscribe_items_changed(self, listener: ChangeListener) -> None:
        """Unsubscribe a listener from items list changes."""
        if listener in self._items_change_listeners:
            self._items_change_listeners.remove(listener)

    def clear_items_changed_listeners(self) -> None:
        """Detach all items-change listeners (e.g. before a panel re-renders)."""
        self._items_change_listeners.clear()

    @property
    def items_changed_listener_count(self) -> int:
        """Return the number of registered items-change listeners."""
        return len(self._items_change_listeners)

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
                return _single_leading_slash(item.label)
            return item.value
        if isinstance(item, SlashCommandItem):
            return _single_leading_slash(item.name)
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

    def get_selected_item(self) -> object | None:
        """Return the currently selected item or None."""
        if (
            not self.items
            or self.selected_index < 0
            or self.selected_index >= len(self.items)
        ):
            return None
        return self.items[self.selected_index]

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
