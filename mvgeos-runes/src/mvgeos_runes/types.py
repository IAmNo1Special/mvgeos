from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from mvgeos_agent.types import MvgeInvocation
    from mvgeos_provider.types import AbortSignal


@runtime_checkable
class Sandbox(Protocol):
    """Structural type for the code-execution sandbox handed to runes.

    The agent layer supplies the concrete implementation (MvgeSandbox);
    runes and the runner depend only on this shape.
    """

    def execute_code(
        self,
        code_str: str,
        context_globals: dict[str, Any] | None = None,
        timeout_seconds: float = 5.0,
        allowed_modules: set[str] | None = None,
    ) -> dict[str, Any]: ...


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
    COMPACTION_START = "compaction_start"
    COMPACTION_END = "compaction_end"
    CONTEXT_TRANSFORM = "context_transform"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    BEFORE_MVGE_START = "before_mvge_start"
    INPUT = "input"
    SHOULD_STOP_AFTER_TURN = "should_stop_after_turn"
    PREPARE_NEXT_TURN = "prepare_next_turn"


@dataclass
class BeforeInvocationData:
    """Data passed to BEFORE_INVOCATION sigil hook."""

    invocation: MvgeInvocation


@dataclass
class AfterInvocationData:
    """Data passed to AFTER_INVOCATION sigil hook."""

    invocation: MvgeInvocation
    stop_reason: str


@dataclass
class BeforeSpellCastData:
    """Data passed to BEFORE_SPELL_CAST sigil hook."""

    spell_cast: dict[str, Any]
    spell_name: str


@dataclass
class AfterSpellResultData:
    """Data passed to AFTER_SPELL_RESULT sigil hook."""

    spell_name: str
    spell_cast_id: str
    result: Any


@dataclass
class BeforeProviderRequestData:
    """Data passed to BEFORE_PROVIDER_REQUEST sigil hook."""

    model: dict[str, Any]


@dataclass
class AfterProviderResponseData:
    """Data passed to AFTER_PROVIDER_RESPONSE sigil hook."""

    response: Any
    mana_used: int


@dataclass
class BeforeProviderHeadersData:
    """Data passed to BEFORE_PROVIDER_HEADERS sigil hook."""

    headers: dict[str, str]


@dataclass
class TurnStartData:
    """Data passed to TURN_START sigil hook."""

    model: dict[str, Any]


@dataclass
class TurnEndData:
    """Data passed to TURN_END sigil hook."""

    stop_reason: str
    mana_used: int


@dataclass
class SessionStartData:
    """Data passed to SESSION_START sigil hook."""

    session_name: str


@dataclass
class SessionShutdownData:
    """Data passed to SESSION_SHUTDOWN sigil hook."""

    session_name: str


@dataclass
class SessionBeforeSwitchData:
    """Data passed to SESSION_BEFORE_SWITCH sigil hook."""

    from_session: str
    to_session: str


@dataclass
class SessionBeforeForkData:
    """Data passed to SESSION_BEFORE_FORK sigil hook."""

    parent_session: str
    child_session: str


@dataclass
class CompactionStartData:
    """Data passed to COMPACTION_START sigil hook."""

    session_name: str
    message_count: int


@dataclass
class CompactionEndData:
    """Data passed to COMPACTION_END sigil hook."""

    session_name: str
    original_count: int
    compacted_count: int


@dataclass
class ContextTransformData:
    """Data passed to CONTEXT_TRANSFORM sigil hook."""

    invocations: list[MvgeInvocation]


@dataclass
class AgentStartData:
    """Data passed to AGENT_START sigil hook."""

    pass


@dataclass
class AgentEndData:
    """Data passed to AGENT_END sigil hook."""

    stop_reason: str


@dataclass
class BeforeMvgeStartData:
    """Data passed to BEFORE_MVGE_START sigil hook."""

    base_prompt: str
    spell_names: list[str]
    config_dir: str
    custom_prompt: str
    agent_name: str
    cwd: str


@dataclass
class InputData:
    """Data passed to INPUT sigil hook."""

    content: str | list[dict[str, Any]] | None


@dataclass
class ShouldStopAfterTurnData:
    """Data passed to SHOULD_STOP_AFTER_TURN sigil hook."""

    pass


@dataclass
class PrepareNextTurnData:
    """Data passed to PREPARE_NEXT_TURN sigil hook."""

    # This will be populated with LoopContext fields
    system_prompt: str = ""
    prompt_source: str = "builtin"
    invocations: list[MvgeInvocation] = field(default_factory=list)
    spell_names: list[str] = field(default_factory=list)
    contemplation_level: str = "medium"
    max_tokens: int | None = None
    temperature: float | None = None
    spell_timeout_ms: int = 30000
    contemplation_budget: int | None = None
    exclude_contemplation: bool = False
    max_turns: int = 50
    queue_mode: str = "one-at-a-time"


# Mapping from SigilHook to its typed data class
SIGIL_HOOK_DATA_CLASSES: dict[SigilHook, type] = {
    SigilHook.BEFORE_INVOCATION: BeforeInvocationData,
    SigilHook.AFTER_INVOCATION: AfterInvocationData,
    SigilHook.BEFORE_SPELL_CAST: BeforeSpellCastData,
    SigilHook.AFTER_SPELL_RESULT: AfterSpellResultData,
    SigilHook.BEFORE_PROVIDER_REQUEST: BeforeProviderRequestData,
    SigilHook.AFTER_PROVIDER_RESPONSE: AfterProviderResponseData,
    SigilHook.BEFORE_PROVIDER_HEADERS: BeforeProviderHeadersData,
    SigilHook.TURN_START: TurnStartData,
    SigilHook.TURN_END: TurnEndData,
    SigilHook.SESSION_START: SessionStartData,
    SigilHook.SESSION_SHUTDOWN: SessionShutdownData,
    SigilHook.SESSION_BEFORE_SWITCH: SessionBeforeSwitchData,
    SigilHook.SESSION_BEFORE_FORK: SessionBeforeForkData,
    SigilHook.COMPACTION_START: CompactionStartData,
    SigilHook.COMPACTION_END: CompactionEndData,
    SigilHook.CONTEXT_TRANSFORM: ContextTransformData,
    SigilHook.AGENT_START: AgentStartData,
    SigilHook.AGENT_END: AgentEndData,
    SigilHook.BEFORE_MVGE_START: BeforeMvgeStartData,
    SigilHook.INPUT: InputData,
    SigilHook.SHOULD_STOP_AFTER_TURN: ShouldStopAfterTurnData,
    SigilHook.PREPARE_NEXT_TURN: PrepareNextTurnData,
}


def create_sigil_data(hook: SigilHook, data: dict[str, Any] | Any) -> Any:
    """Create typed sigil data instance from raw dict or pass through if already typed.

    Args:
        hook: The sigil hook type
        data: Raw dict data or already-typed data instance

    Returns:
        Typed data instance if a mapping exists, otherwise the original data
    """
    data_class = SIGIL_HOOK_DATA_CLASSES.get(hook)
    if data_class is None:
        return data

    # If already an instance of the expected class, return as-is
    if isinstance(data, data_class):
        return data

    # If data is a dict, try to construct the typed instance
    if isinstance(data, dict):
        try:
            return data_class(**data)
        except Exception:
            # Fall back to raw dict if construction fails
            return data

    # For other types, return as-is
    return data


class RuneScope(StrEnum):
    PROJECT = "project"
    USER = "user"
    AGENT = "agent"


class SkillScope(StrEnum):
    PROJECT = "project"
    USER = "user"
    AGENT = "agent"
    LEGACY = "legacy"


@dataclass
class SkillManifest:
    name: str
    description: str
    scope: SkillScope = SkillScope.PROJECT
    path: str = ""
    version: str = ""
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: str = ""
    disable_model_invocation: bool = False


@dataclass
class SkillLoad:
    manifest: SkillManifest


class SkillDiagnosticKind(StrEnum):
    SHADOWED_SKILL = "shadowed_skill"
    PARSE_WARNING = "parse_warning"


@dataclass
class SkillDiagnostic:
    kind: SkillDiagnosticKind
    skill_name: str
    message: str
    scope: SkillScope | None = None
    path: str = ""


class ExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass
class RuneManifest:
    name: str
    version: str
    description: str
    scope: RuneScope = RuneScope.PROJECT
    path: str = ""
    hooks: list[SigilHook] = field(default_factory=list)
    entry_point: str = ""
    shortcuts: list[RuneShortcut] = field(default_factory=list)
    system_deps: list[str] = field(default_factory=list)
    python_deps: list[str] = field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.PARALLEL
    enabled: bool = True


@dataclass(frozen=True)
class RuneContext:
    cwd: str = ""
    mode: str = "cli"
    has_ui: bool = False
    agent_name: str = ""
    api_key: str = ""


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


class DiagnosticKind(StrEnum):
    SHADOWED_RUNE = "shadowed_rune"
    LOAD_FAILURE = "load_failure"
    PARSE_WARNING = "parse_warning"
    MISSING_DEP = "missing_dep"
    INCOMPATIBLE_SESSION = "incompatible_session"
    MODEL_MISMATCH = "model_mismatch"
    MISSING_SPELL = "missing_spell"
    CONTEMPLATION_MISMATCH = "contemplation_mismatch"


@dataclass
class Diagnostic:
    kind: DiagnosticKind
    rune_name: str
    message: str
    scope: RuneScope | None = None
    path: str = ""


@dataclass
class RuneLoad:
    manifest: RuneManifest
    factory: Any = None


class SpellDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        execution_mode: ExecutionMode = ExecutionMode.PARALLEL,
        prompt_snippet: str | None = None,
        prompt_guidelines: list[str] | None = None,
        source_rune: str | None = None,
        handler: Any | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self.execution_mode = execution_mode
        self.prompt_snippet = prompt_snippet
        self.prompt_guidelines = prompt_guidelines or []
        self.source_rune = source_rune
        self._handler = handler

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        if self._handler is not None:
            import inspect

            sig = inspect.signature(self._handler)
            if len(sig.parameters) >= 2 and list(sig.parameters.keys())[0] in (
                "spell_cast_id",
                "id",
            ):
                return cast(
                    dict[str, Any],
                    await self._handler(
                        spell_cast_id, params, signal=signal, on_update=on_update
                    ),
                )
            return cast(
                dict[str, Any],
                await self._handler(params, signal=signal, on_update=on_update),
            )
        raise NotImplementedError
