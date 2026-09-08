from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from mvgeos_provider.model_registry import ModelRegistry

from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.snapshot import RuntimeSnapshot
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    QueueMode,
)


@runtime_checkable
class MvgeAgent(Protocol):
    """Protocol defining the core interface for an Mvge agent.

    Decouples summoning layers (CLI, GUI, runners) from concrete agent
    implementations (such as Mvge).
    """

    @property
    def tome_id(self) -> str | None:
        """The active tome (session) identifier."""
        ...

    @property
    def session_id(self) -> str | None:
        """Alias for tome_id adhering to standard agent protocol vocabulary."""
        ...

    @property
    def model_id(self) -> str:
        """Active model identifier."""
        ...

    @property
    def model_registry(self) -> ModelRegistry:
        """The model registry bound to this agent."""
        ...

    @property
    def contemplation_level(self) -> ContemplationLevel | str:
        """Active contemplation (reasoning effort) level."""
        ...

    @property
    def mana_used(self) -> int | None:
        """Total mana consumed in the current session/state, if available."""
        ...

    @property
    def queue_mode(self) -> QueueMode:
        """Current queue processing mode."""
        ...

    @queue_mode.setter
    def queue_mode(self, mode: QueueMode | str) -> None: ...

    @property
    def registered_providers(self) -> list[str]:
        """List of registered provider/realm names."""
        ...

    @property
    def enabled_spells(self) -> list[str]:
        """List of currently enabled spell names."""
        ...

    @property
    def available_spells(self) -> list[str]:
        """List of all available spell names (builtin + rune-registered)."""
        ...

    def set_enabled_spells(self, spell_names: Sequence[str]) -> None:
        """Filter which spells are enabled for execution."""
        ...

    @property
    def environment(self) -> MvgeEnvironment:
        """The resolved environment configuration."""
        ...

    def on(
        self,
        event_type: MvgeEventType | str,
        callback: Callable[[MvgeEvent], None],
    ) -> Callable[[], None]:
        """Subscribe to agent lifecycle and channeling events."""
        ...

    def steer(self, text: str) -> None:
        """Inject user steering request mid-flight."""
        ...

    def follow_up(self, text: str) -> None:
        """Queue follow-up request after current turn completes."""
        ...

    def abort(self) -> None:
        """Abort active channeling / tool execution."""
        ...

    async def initialize(self) -> None:
        """Wire collaborators, runes, and tome session."""
        ...

    async def run(self, prompt: str) -> MvgeInvocation:
        """Run an invocation turn."""
        ...

    async def switch_model(self, model_id: str) -> None:
        """Switch active model for the running agent."""
        ...

    async def reset_session(self, *, resume_tome_id: str | None = None) -> None:
        """Reset or resume session lifecycle."""
        ...

    def build_snapshot(self) -> RuntimeSnapshot:
        """Assemble runtime snapshot for introspection."""
        ...

    async def close(self) -> None:
        """Shut down resources, runes, and sessions."""
        ...


class AgentFactory(Protocol):
    """Factory protocol for producing MvgeAgent instances."""

    def __call__(self, *args: Any, **kwargs: Any) -> MvgeAgent: ...
