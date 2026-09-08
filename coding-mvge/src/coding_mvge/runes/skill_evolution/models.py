from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EntryType(StrEnum):
    PATTERN = "pattern"
    CONSOLIDATION_LOG = "consolidation_log"


class SkillEvolutionEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    turn: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entry_type: EntryType = EntryType.PATTERN
    tags: list[str] = Field(default_factory=list)
    summary: str
    raw_invocation_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    content: str = ""

    def to_markdown(self) -> str:
        sources = (
            ", ".join(self.raw_invocation_ids) if self.raw_invocation_ids else "none"
        )
        lines = [
            f"# {self.summary}",
            "",
            f"**ID:** {self.id}",
            f"**Turn:** {self.turn}",
            f"**Timestamp:** {self.timestamp.isoformat()}",
            f"**Tags:** {', '.join(self.tags) if self.tags else 'none'}",
            f"**Confidence:** {self.confidence:.2f}",
            f"**Source Invocations:** {sources}",
            "",
            "## Content",
            "",
            self.content or "(no content)",
        ]
        return "\n".join(lines)


class ConsolidationLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    turn: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    traces_processed: int
    entries_created: int
    entries_updated: int
    duration_ms: int
    llm_model: str = ""

    def to_markdown(self) -> str:
        return (
            f"- Turn {self.turn} ({self.timestamp.isoformat()}): "
            f"processed {self.traces_processed} traces, "
            f"created {self.entries_created} entries, "
            f"updated {self.entries_updated} entries "
            f"({self.duration_ms}ms)"
        )


class SkillEvolutionMetadata(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_consolidation_turn: int = 0
    total_entries: int = 0
    total_consolidations: int = 0
    schema_version: int = 1


class ProposalAction(StrEnum):
    CREATE = "create"
    PATCH = "patch"
    NO_ACTION = "no_action"


class PatchOperation(BaseModel):
    op: str
    target: str | None = None
    content: str


class SkillProposal(BaseModel):
    action: ProposalAction
    skill_name: str
    skill_md: str | None = None
    purpose_md: str | None = None
    edits: list[PatchOperation] = Field(default_factory=list)

    @classmethod
    def create_new(
        cls, skill_name: str, skill_md: str, purpose_md: str
    ) -> SkillProposal:
        return cls(
            action=ProposalAction.CREATE,
            skill_name=skill_name,
            skill_md=skill_md,
            purpose_md=purpose_md,
        )

    @classmethod
    def patch_existing(
        cls, skill_name: str, edits: list[PatchOperation]
    ) -> SkillProposal:
        return cls(action=ProposalAction.PATCH, skill_name=skill_name, edits=edits)

    @classmethod
    def no_action(cls) -> SkillProposal:
        return cls(action=ProposalAction.NO_ACTION, skill_name="")


@dataclass
class SkillEvolutionResult:
    success: bool
    action: str
    name: str = ""
    scope: str = ""
    diff: str = ""
    path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "name": self.name,
            "scope": self.scope,
            "diff": self.diff,
            "path": self.path,
            "error": self.error,
        }
