from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

pass

EventHandler = Callable[[Any], Any | None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, channel: str, handler: EventHandler) -> Callable[[], None]:
        self._handlers[channel].append(handler)

        def unsubscribe() -> None:
            self._handlers[channel].remove(handler)

        return unsubscribe

    def emit(self, channel: str, data: Any) -> None:
        for handler in self._handlers.get(channel, []):
            handler(data)
