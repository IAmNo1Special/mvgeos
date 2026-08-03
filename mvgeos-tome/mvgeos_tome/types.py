from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TomeEntryType(StrEnum):
    INVOCATION = "invocation"
    SPELL_RESULT = "spellResult"
    MODEL_CHANGE = "modelChange"
    CONTEMPLATION_LEVEL_CHANGE = "contemplationLevelChange"
    TOOL_CALLS_CHANGE = "toolCallsChange"
    LABEL = "label"
    BRANCH_SUMMARY = "branchSummary"
    COMPACTION = "compaction"
    CUSTOM = "custom"
    CUSTOM_MESSAGE = "customMessage"
    LEAF = "leaf"
    SESSION_INFO = "session_info"
    MESSAGE = "message"


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
