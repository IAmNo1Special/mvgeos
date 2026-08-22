from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mvgeos_agent.types import AbortSignal

from mvgeos_provider.types import ChannelConfig, Model


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
