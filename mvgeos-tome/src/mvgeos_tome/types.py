from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TomeEntryType(StrEnum):
    INVOCATION = "invocation"
    MESSAGE = "message"
    LABEL = "label"
    COMPACTION = "compaction"
    CUSTOM = "custom"
    LEAF = "leaf"
    TOME_INFO = "tome_info"


@dataclass
class TomeEntry:
    id: str
    parent_id: str | None
    type: TomeEntryType
    timestamp: float
    payload: dict[str, Any]


@dataclass
class TomeMetadata:
    id: str
    created_at: str
    cwd: str
    parent_tome_id: str | None = None
    active_leaf_id: str | None = None
    schema_version: str = "1.0"


@dataclass
class TomeIntegrityIssue:
    line_number: int
    message: str
    raw_line: str | None = None


@dataclass
class TomeIntegrityReport:
    valid: bool
    tome_id: str
    issues: list[TomeIntegrityIssue] = field(default_factory=list)
    total_lines: int = 0
    valid_entries_count: int = 0

    def __bool__(self) -> bool:
        return self.valid
