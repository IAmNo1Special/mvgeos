from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

# Canonical definitions of the response/abort vocabulary live in the
# provider layer (transport concerns); re-exported here so the agent's
# public type surface stays stable for downstream packages.
from mvgeos_provider.types import (
    AbortController as AbortController,
)
from mvgeos_provider.types import (
    AbortError as AbortError,
)
from mvgeos_provider.types import (
    AbortSignal as AbortSignal,
)
from mvgeos_provider.types import (
    MvgeResponse as MvgeResponse,
)
from mvgeos_provider.types import (
    StopReason as StopReason,
)
from mvgeos_runes.types import ExecutionMode
from pydantic import BaseModel, ValidationError, create_model

from mvgeos_agent.errors import (
    TomeIncompatibleError as TomeIncompatibleError,
)
from mvgeos_agent.errors import (
    TomeResumeError as TomeResumeError,
)

SpellExecutionMode = ExecutionMode

if TYPE_CHECKING:
    from mvgeos_runes.rune_runner import RuneRunner

    from mvgeos_agent.agent_session import MvgeTome
    from mvgeos_agent.event_bus import EventBus


class PromptSource(StrEnum):
    """Where a resolved prompt resource came from."""

    CUSTOM_LITERAL = "custom_literal"
    CUSTOM_PATH = "custom_path"
    PROJECT_MD = "project_md"
    AGENT_MD = "agent_md"
    BUILTIN = "builtin"


class ContentType(StrEnum):
    TEXT = "text"
    SPELL_CAST = "spell_cast"
    CONTEMPLATION = "contemplation"


class ContemplationLevel(StrEnum):
    OFF = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class QueueMode(StrEnum):
    ALL = "all"
    ONE_AT_A_TIME = "one-at-a-time"


class MvgeEventType(StrEnum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    INPUT = "input"
    BEFORE_PROVIDER_REQUEST = "before_provider_request"
    AFTER_PROVIDER_RESPONSE = "after_provider_response"
    BEFORE_INVOCATION = "before_invocation"
    AFTER_INVOCATION = "after_invocation"
    MESSAGE_START = "message_start"
    MESSAGE_UPDATE = "message_update"
    MESSAGE_END = "message_end"
    SPELL_CASTING_START = "spell_casting_start"
    SPELL_CASTING_END = "spell_casting_end"
    ARTIFACT_CREATED = "artifact_created"
    COMPACTION_START = "compaction_start"
    COMPACTION_END = "compaction_end"
    PROVIDER_ERROR = "provider_error"


@dataclass
class SummonerRequest:
    role: str = "user"
    content: str | list[dict[str, Any]] | None = None
    timestamp: float = 0.0


class SpellStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


@dataclass
class SpellResult:
    spell_name: str
    status: SpellStatus = SpellStatus.SUCCESS
    content: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    terminate: bool = False


@dataclass
class SpellResultMessage:
    role: str = "spellResult"
    spell_cast_id: str = ""
    spell_name: str = ""
    content: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] | None = None
    is_error: bool = False
    timestamp: float = 0.0
    terminate: bool = False


MvgeInvocation = SummonerRequest | MvgeResponse | SpellResultMessage


class SpellSignal(Protocol):
    cancelled: bool

    def cancel(self) -> None: ...

    def raise_if_aborted(self) -> None: ...


SpellUpdateCallback = Callable[[dict[str, Any]], None]


@dataclass
class MvgeSpell:
    name: str
    description: str
    parameters: dict[str, Any]
    execution_mode: SpellExecutionMode = SpellExecutionMode.PARALLEL
    _schema_model: type[BaseModel] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.parameters:
            self._schema_model = create_model(
                f"{self.name}_Schema",
                **self._convert_to_model_fields(self.parameters),
            )

    def _convert_to_model_fields(self, params: dict[str, Any]) -> dict[str, Any]:
        """Convert JSON Schema properties to Pydantic model fields."""
        fields = {}
        props = params.get("properties", {})
        required = params.get("required", [])
        for name, prop in props.items():
            field_type = self._json_type_to_python(prop)
            # Use the field type directly; Pydantic infers optional from default
            fields[name] = (field_type, ... if name in required else None)
        return fields

    def _json_type_to_python(self, prop: dict[str, Any]) -> type:
        """Convert JSON Schema type to Python type."""
        json_type = prop.get("type")
        if not json_type and "anyOf" in prop:
            types = [
                t.get("type")
                for t in prop["anyOf"]
                if isinstance(t, dict) and t.get("type") != "null"
            ]
            if "integer" in types:
                return int
            if "number" in types:
                return float
            if "boolean" in types:
                return bool
            if "array" in types:
                return list[Any]
            if "object" in types:
                return dict[str, Any]
            json_type = "string"

        if json_type == "string":
            return str
        elif json_type == "integer":
            return int
        elif json_type == "number":
            return float
        elif json_type == "boolean":
            return bool
        elif json_type == "array":
            items = prop.get("items", {})
            if items:
                _ = self._json_type_to_python(items)
                # Use list[Any] and let Pydantic handle validation at runtime
                return list[Any]
            return list[Any]
        elif json_type == "object":
            return dict[str, Any]
        return Any

    def prepare_arguments(self, args: dict[str, Any]) -> dict[str, Any]:
        if self._schema_model is None:
            return args
        try:
            validated = self._schema_model.model_validate(args)
            return validated.model_dump()
        except ValidationError as e:
            raise ValueError(f"Invalid arguments for spell {self.name}: {e}") from e

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any] | str | SpellResult:
        raise NotImplementedError


@dataclass
class MvgeState:
    system_prompt: str = ""
    prompt_source: PromptSource = PromptSource.BUILTIN
    model: dict[str, Any] | None = None
    contemplation_level: ContemplationLevel = ContemplationLevel.MEDIUM
    spells: list[MvgeSpell] = field(default_factory=list)
    _spell_index: dict[str, MvgeSpell] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    invocations: list[MvgeInvocation] = field(default_factory=list)
    is_streaming: bool = False
    streaming_manifestation: MvgeInvocation | None = None
    pending_spell_casts: set[str] = field(default_factory=set)
    error_message: str | None = None
    mana_used: int = 0
    max_tokens: int | None = None
    temperature: float | None = None
    max_turns: int = 50
    max_events: int = 1000
    spell_timeout_ms: int = 30000
    contemplation_budget: int | None = None
    exclude_contemplation: bool = False
    queue_mode: QueueMode = QueueMode.ONE_AT_A_TIME
    rune_runner: RuneRunner | None = None
    agent_tome: MvgeTome | None = None
    event_bus: EventBus | None = None
    events: list[MvgeEvent] = field(default_factory=list)
    steer_queue: list[SummonerRequest] = field(default_factory=list)
    followup_queue: list[SummonerRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._spell_index = {s.name: s for s in self.spells}


@dataclass
class MvgeEvent:
    type: MvgeEventType
    data: dict[str, Any] = field(default_factory=dict)


class SandboxTimeoutError(Exception):
    """Raised when sandbox code execution exceeds the timeout threshold."""
