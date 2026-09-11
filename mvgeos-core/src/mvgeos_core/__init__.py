"""Canonical loop vocabulary for MvgeOS.

Zero first-party dependencies. Leaf packages (provider, runes, tome) and the
agent depend on core, never the reverse.
"""

from mvgeos_core.abort import AbortController, AbortError, AbortSignal
from mvgeos_core.channel import (
    ChannelConfig,
    Model,
    MvgeResponse,
    RealmResponse,
    StopReason,
)
from mvgeos_core.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL,
    DEFAULT_RUNE_PATHS,
    DEFAULT_TOME_DIR,
    resolve_rune_paths,
)
from mvgeos_core.dispatcher import BatchResult, SpellDispatcher
from mvgeos_core.errors import (
    AuthenticationError,
    MaxTurnsExceededError,
    MissingApiKeyError,
    MvgeError,
    RateLimitError,
    SpellDiscoveryError,
    SpellNotFoundError,
    SpellTimeoutError,
    TomeIncompatibleError,
    TomeResumeError,
    UpstreamTimeoutError,
    to_error,
)
from mvgeos_core.event_bus import EventBus
from mvgeos_core.events import (
    ContemplationLevel,
    ContentType,
    MvgeEvent,
    MvgeEventType,
    PromptSource,
    QueueMode,
)
from mvgeos_core.invocations import MvgeInvocation, SummonerRequest
from mvgeos_core.loop import (
    EmitSink,
    LoopCallbacks,
    LoopContext,
    StreamFn,
    run_loop,
)
from mvgeos_core.sandbox import MvgeSandbox, SandboxTimeoutError
from mvgeos_core.spell_schema import generate_spell_schema
from mvgeos_core.spells import (
    ExecutionMode,
    MvgeSpell,
    SpellExecutionMode,
    SpellResult,
    SpellResultMessage,
    SpellSignal,
    SpellStatus,
    SpellUpdateCallback,
)

__all__ = [
    "AbortController",
    "AbortError",
    "AbortSignal",
    "AuthenticationError",
    "BatchResult",
    "ChannelConfig",
    "ContemplationLevel",
    "ContentType",
    "DEFAULT_AGENT_NAME",
    "DEFAULT_MODEL",
    "DEFAULT_RUNE_PATHS",
    "DEFAULT_TOME_DIR",
    "EmitSink",
    "EventBus",
    "ExecutionMode",
    "LoopCallbacks",
    "LoopContext",
    "MaxTurnsExceededError",
    "MissingApiKeyError",
    "Model",
    "MvgeError",
    "MvgeEvent",
    "MvgeEventType",
    "MvgeInvocation",
    "MvgeResponse",
    "MvgeSandbox",
    "MvgeSpell",
    "PromptSource",
    "QueueMode",
    "RateLimitError",
    "RealmResponse",
    "SandboxTimeoutError",
    "SpellDispatcher",
    "SpellDiscoveryError",
    "SpellExecutionMode",
    "SpellNotFoundError",
    "SpellResult",
    "SpellResultMessage",
    "SpellSignal",
    "SpellStatus",
    "SpellTimeoutError",
    "SpellUpdateCallback",
    "StopReason",
    "StreamFn",
    "SummonerRequest",
    "TomeIncompatibleError",
    "TomeResumeError",
    "UpstreamTimeoutError",
    "generate_spell_schema",
    "resolve_rune_paths",
    "run_loop",
]
