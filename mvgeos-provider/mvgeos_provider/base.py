from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from mvgeos_provider.types import ChannelConfig, Model


class Realm:
    def stream(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
    ) -> AsyncIterator[Any]:
        raise NotImplementedError

    async def close(self) -> None:
        pass
