from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SigilHook(StrEnum):
    BEFORE_INVOCATION = "before_invocation"
    AFTER_INVOCATION = "after_invocation"
    BEFORE_SPELL_CAST = "before_spell_cast"
    AFTER_SPELL_RESULT = "after_spell_result"
    BEFORE_PROVIDER_REQUEST = "before_provider_request"
    AFTER_PROVIDER_RESPONSE = "after_provider_response"
    BEFORE_PROVIDER_HEADERS = "before_provider_headers"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    SESSION_START = "session_start"
    SESSION_SHUTDOWN = "session_shutdown"
    SESSION_BEFORE_SWITCH = "session_before_switch"
    SESSION_BEFORE_FORK = "session_before_fork"
    CONTEXT_TRANSFORM = "context_transform"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    INPUT = "input"


@dataclass
class RuneManifest:
    name: str
    version: str
    description: str
    hooks: list[SigilHook] = field(default_factory=list)
    entry_point: str = ""
    shortcuts: list[RuneShortcut] = field(default_factory=list)


class ExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass
class RuneContext:
    cwd: str = ""
    mode: str = "cli"
    has_ui: bool = False


@dataclass
class RegisteredCommand:
    name: str
    description: str = ""
    handler: Any = None


@dataclass
class RuneShortcut:
    key: str
    description: str = ""
    handler: Any = None


class SpellDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        execution_mode: ExecutionMode = ExecutionMode.PARALLEL,
        prompt_snippet: str | None = None,
        prompt_guidelines: list[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self.execution_mode = execution_mode
        self.prompt_snippet = prompt_snippet
        self.prompt_guidelines = prompt_guidelines or []

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError
