"""Diff-related models: hunks, lines, parsed diff views, changed files."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiffLine:
    """A single line within a diff hunk with type and line number context."""

    content: str
    line_type: str = "context"
    old_line_number: int | None = None
    new_line_number: int | None = None


@dataclass
class DiffHunk:
    """A contiguous block of changes within a unified diff."""

    source_start: int = 0
    source_length: int = 0
    target_start: int = 0
    target_length: int = 0
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class DiffView:
    """Parsed diff representation for a single file."""

    file_path: str
    status: str = "modified"
    hunks: list[DiffHunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


@dataclass
class ChangedFile:
    """Summary of a changed file with addition/deletion counts."""

    path: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
