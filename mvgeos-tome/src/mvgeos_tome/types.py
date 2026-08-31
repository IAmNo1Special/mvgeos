from __future__ import annotations

from dataclasses import dataclass
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
