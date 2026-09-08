from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

CURRENT_SESSION_VERSION: int = 3


class TomeEntryType(StrEnum):
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parentId": self.parent_id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class TomeVersionError(Exception):
    """Raised when encountering an unsupported or invalid session schema version."""

    def __init__(self, version: Any, message: str | None = None) -> None:
        self.version = version
        msg = message or f"Unsupported session version: {version}"
        super().__init__(msg)


@dataclass
class TomeMetadata:
    id: str
    created_at: str
    cwd: str
    parent_tome_id: str | None = None
    active_leaf_id: str | None = None
    schema_version: str = "1.0"
    version: int = 3
    model: str | None = None
    contemplation_level: str | None = None
    spells: list[str] = field(default_factory=list)


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
