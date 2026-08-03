from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mvgeos_runes.types import SigilHook

Handler = Callable[..., Any | None | Awaitable[Any | None]]


class SigilRegistry:
    def __init__(self) -> None:
        self._handlers: dict[SigilHook, list[Handler]] = {}

    def register(self, hook: SigilHook, handler: Handler) -> None:
        if hook not in self._handlers:
            self._handlers[hook] = []
        self._handlers[hook].append(handler)

    def get_handlers(self, hook: SigilHook) -> list[Handler]:
        return self._handlers.get(hook, [])

    @property
    def handlers(self) -> dict[SigilHook, list[Handler]]:
        return self._handlers
