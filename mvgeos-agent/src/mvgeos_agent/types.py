from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ValidationError

from mvgeos_agent.prompt_loader import PromptSource

if TYPE_CHECKING:
    from mvgeos_runes.rune_runner import RuneRunner

    from mvgeos_agent.agent_session import MvgeTome
    from mvgeos_agent.event_bus import EventBus


class ContentType(StrEnum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    CONTEMPLATION = "contemplation"


class ContemplationLevel(StrEnum):
    OFF = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class SpellExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class QueueMode(StrEnum):
    ALL = "all"
    ONE_AT_A_TIME = "one-at-a-time"


class MvgeEventType(StrEnum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_SETTLED = "agent_settled"
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
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_UPDATE = "tool_execution_update"
    TOOL_EXECUTION_END = "tool_execution_end"
    SPELL_CASTING_START = "spell_casting_start"
    SPELL_CASTING_UPDATE = "spell_casting_update"
    SPELL_CASTING_END = "spell_casting_end"
    ARTIFACT_CREATED = "artifact_created"
    COMPACTION_START = "compaction_start"
    COMPACTION_END = "compaction_end"
    ENTRY_APPENDED = "entry_appended"
    QUEUE_UPDATE = "queue_update"


class StopReason(StrEnum):
    PENDING = "pending"
    STOP = "stop"
    LENGTH = "length"
    SPELL_USE = "spellUse"
    ERROR = "error"
    ABORTED = "aborted"


@dataclass
class SummonerRequest:
    role: str = "user"
    content: str | list[dict[str, Any]] | None = None
    timestamp: float = 0.0


@dataclass
class MvgeResponse:
    role: str = "assistant"
    content: list[dict[str, Any]] = field(default_factory=list)
    realm: str = ""
    model: str = ""
    mana_usage: dict[str, float] = field(default_factory=dict)
    stop_reason: StopReason = StopReason.PENDING
    error_message: str | None = None
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


class AbortError(Exception):
    """Raised when an operation is cancelled via AbortSignal."""


class AbortSignal:
    """Cancellation signal, mirroring the web AbortSignal API (Pi-compatible).

    A signal is created with ``aborted`` False. Calling ``controller.abort()``
    flips the flag and fires any registered callbacks. Consumers should check
    ``aborted`` or call ``raise_if_aborted()`` at safe checkpoints.
    """

    def __init__(self, controller: AbortController) -> None:
        self._controller = controller
        self._aborted = False
        self._callbacks: list[Callable[[], None]] = []
        self._wait_future: asyncio.Future[None] | None = None

    @property
    def aborted(self) -> bool:
        return self._aborted

    def on_abort(self, callback: Callable[[], None]) -> None:
        if self._aborted:
            callback()
        else:
            self._callbacks.append(callback)

    def raise_if_aborted(self) -> None:
        if self._aborted:
            raise AbortError("Operation aborted")

    async def wait(self) -> None:
        """Block until the signal is aborted or the await is cancelled.

        Multiple concurrent calls to wait() will all resolve when the signal is aborted.
        """
        if self._aborted:
            return
        if self._wait_future is not None and not self._wait_future.done():
            await self._wait_future
            return
        self._wait_future = asyncio.get_event_loop().create_future()

        def _set_result() -> None:
            if self._wait_future is not None and not self._wait_future.done():
                self._wait_future.set_result(None)

        self._callbacks.append(_set_result)
        try:
            await self._wait_future
        finally:
            if _set_result in self._callbacks:
                self._callbacks.remove(_set_result)

    @classmethod
    def _none(cls) -> AbortSignal:
        """Return a signal that is never aborted and has no controller."""
        return _NullAbortSignal()


class _NullAbortSignal(AbortSignal):
    """Null object pattern for a never-aborted signal."""

    def __init__(self) -> None:
        # Bypass parent init - this signal is never aborted
        pass

    @property
    def aborted(self) -> bool:
        return False

    def on_abort(self, callback: Callable[[], None]) -> None:
        pass  # Never fires

    def raise_if_aborted(self) -> None:
        pass  # Never raises

    async def wait(self) -> None:
        # Wait forever (or until cancelled)
        await asyncio.Event().wait()


class AbortController:
    """Controller that owns an :class:`AbortSignal` and can abort it.

    Mirrors the web ``AbortController`` API and Pi's cancellation model.
    """

    def __init__(self) -> None:
        self._signal = AbortSignal(self)

    @property
    def signal(self) -> AbortSignal:
        return self._signal

    def abort(self) -> None:
        if self._signal._aborted:
            return
        self._signal._aborted = True
        for callback in list(self._signal._callbacks):
            with contextlib.suppress(Exception):
                callback()
        self._signal._callbacks.clear()
        wait_future = self._signal._wait_future
        if wait_future is not None and not wait_future.done():
            wait_future.set_result(None)


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
            from pydantic import create_model

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
    ) -> dict[str, Any] | str:
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


class TomeResumeError(Exception):
    """Raised when resuming a tome fails."""


@dataclass
class MvgeEvent:
    type: MvgeEventType
    data: dict[str, Any] = field(default_factory=dict)


class SandboxTimeoutError(Exception):
    """Raised when sandbox code execution exceeds the timeout threshold."""
