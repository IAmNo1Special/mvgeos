"""Data models for mvgeos-gui.

This package re-exports all public types from the individual model modules so
that existing imports continue to work:

    from mvgeos_gui.models import ChatMessage, Artifact, DiffView
"""

from mvgeos_gui.models.artifact import Artifact, ArtifactType
from mvgeos_gui.models.diff import ChangedFile, DiffHunk, DiffLine, DiffView
from mvgeos_gui.models.execution import (
    BackgroundTask,
    CommandExecution,
    ExecutionStep,
    FileExploration,
    StepType,
    TaskStatus,
)
from mvgeos_gui.models.message import ChatMessage, MessagePart, MessagePartType
from mvgeos_gui.models.session import Session
from mvgeos_gui.models.skill import SkillInfo
from mvgeos_gui.models.user import User

__all__ = [
    "Artifact",
    "ArtifactType",
    "BackgroundTask",
    "ChangedFile",
    "ChatMessage",
    "CommandExecution",
    "DiffHunk",
    "DiffLine",
    "DiffView",
    "ExecutionStep",
    "FileExploration",
    "MessagePart",
    "MessagePartType",
    "Session",
    "SkillInfo",
    "StepType",
    "TaskStatus",
    "User",
]
