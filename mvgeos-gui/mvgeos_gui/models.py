"""Data models for conversation messages and execution steps in mvgeos-gui."""

from __future__ import annotations

import re
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
    contemplation: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).strftime("%H:%M"))
    model: str | None = None
    mana_used: int = 0
    is_streaming: bool = False
    steps: list[ExecutionStep] = field(default_factory=list)
    feedback: str | None = None
    is_error: bool = False
    error_message: str | None = None


def extract_contemplation_tags(text: str) -> tuple[str, str]:
    """Extract <think>...</think> or <thought>...</thought> tags from text.

    Returns (cleaned_content, extracted_contemplation).
    """
    if not text:
        return "", ""

    pattern = re.compile(
        r"<(?:think|thought)>(.*?)</(?:think|thought)>",
        re.DOTALL | re.IGNORECASE,
    )
    thoughts: list[str] = []

    def _replace(m: re.Match[str]) -> str:
        thoughts.append(m.group(1).strip())
        return ""

    cleaned = pattern.sub(_replace, text)

    # Check for unclosed <think> or <thought> tag at end of streaming buffer
    unclosed = re.compile(
        r"<(?:think|thought)>(.*)$",
        re.DOTALL | re.IGNORECASE,
    )
    unclosed_match = unclosed.search(cleaned)
    if unclosed_match:
        thoughts.append(unclosed_match.group(1).strip())
        cleaned = unclosed.sub("", cleaned)

    extracted_thoughts = "\n\n".join(t for t in thoughts if t)
    return cleaned.strip(), extracted_thoughts
