from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from mvgeos_core.abort import AbortSignal
from mvgeos_core.channel import (
    ChannelConfig,
    Model,
)
from mvgeos_core.errors import MvgeError


class NoRealmRegisteredError(MvgeError):
    """Raised when no Realm factory is registered for a requested model.

    ``realm`` and ``rune_name`` are carried as attributes rather than left for
    the caller to recover from the message. Both of the surfaces that act on this
    -- the CLI install prompt and the GUI badge -- used to split the message on
    ``"install "`` to find the Rune name, which couples them to the wording and
    fails quietly if it changes.
    """

    def __init__(self, message: str, realm: str = "", rune_name: str = "") -> None:
        super().__init__("no_realm_registered", message)
        self.realm = realm
        self.rune_name = rune_name


class Realm:
    @property
    def is_router(self) -> bool:
        """Return True if this realm routes requests to multiple upstream providers."""
        return False

    def stream(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
        signal: AbortSignal | None = None,
    ) -> AsyncIterator[Any]:
        raise NotImplementedError

    async def complete(
        self,
        model: Model,
        messages: list[dict[str, Any]],
        config: ChannelConfig,
        signal: AbortSignal | None = None,
    ) -> Any:
        """Run one non-channelled request and return the whole response.

        Used for standalone calls that are not part of a Tome's transcript,
        such as generating a compaction summary. Takes wire-format messages
        rather than Invocations because the caller composes the prompt.
        """
        raise NotImplementedError

    async def close(self) -> None:
        pass


@runtime_checkable
class RealmFactory(Protocol):
    """Protocol for factories that construct Realm instances."""

    def __call__(
        self,
        api_key: str = "",
        base_url: str = "",
        **kwargs: Any,
    ) -> Realm:
        """Create and return a configured Realm instance."""
        ...


__all__ = [
    "NoRealmRegisteredError",
    "Realm",
    "RealmFactory",
]
