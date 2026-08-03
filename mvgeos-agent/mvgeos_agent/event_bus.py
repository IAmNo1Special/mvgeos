from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mvgeos_agent.types import MvgeEvent, MvgeEventType


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[MvgeEventType, list[Callable[[MvgeEvent], None]]] = {}

    def on(
        self,
        event_type: MvgeEventType,
        callback: Callable[[MvgeEvent], None],
    ) -> Callable[[], None]:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

        def unsubscribe() -> None:
            listeners = self._listeners.get(event_type, [])
            if callback in listeners:
                listeners.remove(callback)

        return unsubscribe

    def emit(self, event_type: MvgeEventType, data: dict[str, Any]) -> None:
        event = MvgeEvent(type=event_type, data=data)
        for listener in self._listeners.get(event_type, []):
            listener(event)
