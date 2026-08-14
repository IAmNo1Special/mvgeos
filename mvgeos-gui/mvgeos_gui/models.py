"""Data models for conversation messages and execution steps in mvgeos-gui."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class StepType(StrEnum):
    """Categorized type of an intermediate agent execution step."""

    WORKED = "worked"
    FILES = "files"
    COMMANDS = "commands"


@dataclass
class CommandExecution:
    """Execution details of a shell command invocation."""

    command: str
    output: str = ""
    exit_code: int = 0
    is_error: bool = False
    duration_seconds: float = 0.0


@dataclass
class FileExploration:
    """Exploration details of a file or directory operation."""

    path: str
    operation: str = "read"
    lines: str | None = None
    details: str | None = None
    is_error: bool = False


@dataclass
class ExecutionStep:
    """A collapsible execution card grouping internal operations."""

    step_type: StepType
    title: str = ""
    duration_seconds: float = 0.0
    commands: list[CommandExecution] = field(default_factory=list)
    files: list[FileExploration] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    is_complete: bool = False


@dataclass
class ChatMessage:
    """A single chat message in the conversation thread."""

    role: str
    content: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).strftime("%H:%M"))
    model: str | None = None
    mana_used: int = 0
    is_streaming: bool = False
    steps: list[ExecutionStep] = field(default_factory=list)
    feedback: str | None = None
    is_error: bool = False
    error_message: str | None = None
