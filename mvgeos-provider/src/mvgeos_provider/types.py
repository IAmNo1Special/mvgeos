from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StopReason(StrEnum):
    PENDING = "pending"
    STOP = "stop"
    LENGTH = "length"
    SPELL_USE = "spellUse"
    ERROR = "error"
    ABORTED = "aborted"


@dataclass
class MvgeResponse:
    role: str = "assistant"
    content: list[dict[str, Any]] = field(default_factory=list)
    realm: str = ""
    model: str = ""
    mana_usage: dict[str, float] = field(default_factory=dict)
    stop_reason: StopReason = StopReason.PENDING
    error_message: str | None = None
    timestamp: float = 0.0


class AbortError(Exception):
    """Raised when an operation is cancelled via AbortSignal."""


class AbortSignal:
    """Cancellation signal, mirroring the web AbortSignal API (Pi-compatible).

    A signal is created with ``aborted`` False. Calling ``controller.abort()``
    flips the flag and fires any registered callbacks. Consumers should check
    ``aborted`` or call ``raise_if_aborted()`` at safe checkpoints.
    """

    def __init__(self, controller: AbortController) -> None:
        self._controller = controller
        self._aborted = False
        self._callbacks: list[Callable[[], None]] = []
        self._wait_future: asyncio.Future[None] | None = None

    @property
    def aborted(self) -> bool:
        return self._aborted

    def on_abort(self, callback: Callable[[], None]) -> None:
        if self._aborted:
            callback()
        else:
            self._callbacks.append(callback)

    def raise_if_aborted(self) -> None:
        if self._aborted:
            raise AbortError("Operation aborted")

    async def wait(self) -> None:
        """Block until the signal is aborted or the await is cancelled.

        Multiple concurrent calls to wait() will all resolve when the signal is aborted.
        """
        if self._aborted:
            return
        if self._wait_future is not None and not self._wait_future.done():
            await self._wait_future
            return
        self._wait_future = asyncio.get_event_loop().create_future()

        def _set_result() -> None:
            if self._wait_future is not None and not self._wait_future.done():
                self._wait_future.set_result(None)

        self._callbacks.append(_set_result)
        try:
            await self._wait_future
        finally:
            if _set_result in self._callbacks:
                self._callbacks.remove(_set_result)


class AbortController:
    """Controller that owns an :class:`AbortSignal` and can abort it.

    Mirrors the web ``AbortController`` API and Pi's cancellation model.
    """

    def __init__(self) -> None:
        self._signal = AbortSignal(self)

    @property
    def signal(self) -> AbortSignal:
        return self._signal

    def abort(self) -> None:
        if self._signal._aborted:
            return
        self._signal._aborted = True
        for callback in list(self._signal._callbacks):
            with contextlib.suppress(Exception):
                callback()
        self._signal._callbacks.clear()
        wait_future = self._signal._wait_future
        if wait_future is not None and not wait_future.done():
            wait_future.set_result(None)


@dataclass
class Model:
    id: str
    name: str
    realm: str
    base_url: str
    api_key: str
    max_completion_mana: int = 0
    context_window: int = 128000
    max_tokens: int = 4096
    headers: dict[str, str] = field(default_factory=dict)
    supported_parameters: list[str] = field(default_factory=list)
    is_free: bool = False

    @property
    def free(self) -> bool:
        """Return True if the model is free of charge."""
        return self.is_free or self.id.endswith(":free") or self.id == "openrouter/free"

    @property
    def provider(self) -> str:
        """The organization that provides this model (derived from the model ID)."""
        return self.id.split("/")[0] if "/" in self.id else self.realm


@dataclass
class ChannelConfig:
    model: Model
    temperature: float = 0.7
    max_tokens: int = 4096
    max_output_mana: int | None = None
    timeout_ms: int = 60000
    max_retries: int = 3
    contemplation_level: str = "medium"
    contemplation_budget: int | None = None
    exclude_contemplation: bool = False
    tools: list[dict[str, Any]] = field(default_factory=list)
    meta_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealmResponse:
    model: Model
    invocation: Any | None = None
    mana_used: int = 0
    stop_reason: str = "stop"
    error_message: str | None = None
    error_code: str | None = None
