from __future__ import annotations

from typing import Any

from mvgeos_runes.types import SigilHook


class SigilRegistry:
    def __init__(self) -> None:
        self._handlers: dict[SigilHook, list[Any]] = {}

    def register(self, hook: SigilHook, handler: Any) -> None:
        if hook not in self._handlers:
            self._handlers[hook] = []
        self._handlers[hook].append(handler)

    def emit(self, hook: SigilHook, data: Any) -> None:
        for handler in self._handlers.get(hook, []):
            if hasattr(handler, hook.value):
                getattr(handler, hook.value)(data)
