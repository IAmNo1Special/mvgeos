from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from mvgeos_core.abort import AbortSignal
from mvgeos_core.channel import (
    ChannelConfig,
    Model,
)


class Realm:
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
    "Realm",
    "RealmFactory",
]
