"""Retry policy for Realm calls.

Two layers, mirroring Pi:

- `retry_realm_request` retries a single HTTP request against a Realm. It honours
  server-supplied `Retry-After` headers and backs off with capped, jittered
  exponential delay.
- `retry_invocation` retries a whole Invocation. Realms report transient trouble
  as a `RealmResponse` carrying an error rather than raising, so this layer
  classifies the response instead of catching exceptions.

Both take an optional `signal` (AbortSignal). When aborted, retry loops exit
promptly by raising AbortError.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from mvgeos_provider.types import AbortError, RealmResponse

DEFAULT_MAX_RETRY_DELAY_MS = 60_000
_MAX_BACKOFF_MS = 8_000
_BACKOFF_BASE_MS = 500
_JITTER_FRACTION = 0.25

_RETRYABLE_STATUSES = (408, 409, 429)

# Realm/transport wording that indicates a transient failure worth retrying.
_RETRYABLE_PATTERNS = (
    "overloaded",
    "rate.?limit",
    "too many requests",
    "429",
    "500",
    "502",
    "503",
    "504",
    "524",
    "service.?unavailable",
    "server.?error",
    "internal.?error",
    "provider.?returned.?error",
    "network.?error",
    "connection.?error",
    "connection.?refused",
    "connection.?lost",
    "other side closed",
    "fetch failed",
    "getaddrinfo",
    "ENOTFOUND",
    "EAI_AGAIN",
    "upstream.?connect",
    "reset before headers",
    "socket hang up",
    "socket connection was closed",
    "timed? out",
    "timeout",
    "terminated",
    "websocket.?closed",
    "websocket.?error",
    "ended without",
    "stream ended before",
    "http2 request did not get a response",
    "retry delay",
    "you can retry your request",
    "try your request again",
    "please retry your request",
    "ResourceExhausted",
)

# Account limits and billing failures. Deterministic, so never retried, even
# when the wording also matches a transient pattern.
_NON_RETRYABLE_PATTERNS = (
    "GoUsageLimitError",
    "FreeUsageLimitError",
    "Monthly usage limit reached",
    "available balance",
    "insufficient_quota",
    "out of budget",
    "quota exceeded",
    "billing",
)

_RETRYABLE_RE = re.compile("|".join(_RETRYABLE_PATTERNS), re.IGNORECASE)
_NON_RETRYABLE_RE = re.compile("|".join(_NON_RETRYABLE_PATTERNS), re.IGNORECASE)

# Error codes a Realm sets explicitly. Trusted ahead of the prose patterns.
_RETRYABLE_CODES = frozenset({"rate_limited"})
_NON_RETRYABLE_CODES = frozenset({"auth_failed"})


class ServerRetryDelayTooLongError(Exception):
    """Raised when a Realm asks for a longer retry delay than we will wait."""

    def __init__(self, delay_ms: float, max_delay_ms: float) -> None:
        super().__init__(
            f"Realm requested {delay_ms / 1000:.0f}s retry delay "
            f"(max: {max_delay_ms / 1000:.0f}s)"
        )
        self.delay_ms = delay_ms
        self.max_delay_ms = max_delay_ms


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded attempts with exponential backoff."""

    enabled: bool = True
    max_retries: int = 3
    base_delay_ms: float = 1000.0


DEFAULT_RETRY_POLICY = RetryPolicy()


@dataclass
class RetryCallbacks:
    """Optional hooks fired around each retry. None of these may raise."""

    on_retry_scheduled: Callable[[int, int, float, str], Awaitable[None]] | None = None
    on_retry_attempt_start: Callable[[], Awaitable[None]] | None = None
    on_retry_finished: Callable[[bool, int, str | None], Awaitable[None]] | None = None


class _HeaderLike(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...


def is_retryable_realm_response(response: RealmResponse) -> bool:
    """Whether a failed Realm response looks transient enough to retry.

    A Realm-supplied `error_code` is authoritative. Otherwise the error prose is
    matched against known-deterministic patterns first, then transient ones.
    """
    if not response.error_message:
        return False

    code = response.error_code
    if code in _NON_RETRYABLE_CODES:
        return False
    if code in _RETRYABLE_CODES:
        return True

    if _NON_RETRYABLE_RE.search(response.error_message):
        return False
    return bool(_RETRYABLE_RE.search(response.error_message))


async def _sleep_ms(delay_ms: float, signal: Any | None = None) -> None:
    """Sleep for delay_ms, respecting abort signal.

    If multiple calls to _sleep_ms share the same signal, all will be cancelled
    when the signal is aborted. This is intentional shared-cancellation behavior.
    """
    if delay_ms <= 0:
        return
    if signal is not None and signal.aborted:
        raise AbortError("Operation aborted")
    sleep_task = asyncio.create_task(asyncio.sleep(delay_ms / 1000))

    def _on_abort() -> None:
        if not sleep_task.done():
            sleep_task.cancel()

    if signal is not None:
        signal.on_abort(_on_abort)
        if signal.aborted:
            raise AbortError("Operation aborted")
    try:
        await sleep_task
    except asyncio.CancelledError:
        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted") from None
        raise


async def retry_invocation(
    produce: Callable[[], Awaitable[RealmResponse]],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    callbacks: RetryCallbacks | None = None,
    signal: Any | None = None,
) -> RealmResponse:
    """Run an Invocation, retrying transient Realm failures.

    Returns the first successful response, or the final failure once retries are
    exhausted or the error is classified as deterministic.
    """
    max_attempts = policy.max_retries if policy.enabled else 0
    attempt = 0
    last_error: str | None = None

    while True:
        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted")
        response = await produce()

        if not response.error_message:
            if last_error is not None and callbacks and callbacks.on_retry_finished:
                await callbacks.on_retry_finished(True, attempt, None)
            return response

        if attempt >= max_attempts or not is_retryable_realm_response(response):
            if last_error is not None and callbacks and callbacks.on_retry_finished:
                await callbacks.on_retry_finished(
                    False, attempt, response.error_message
                )
            return response

        attempt += 1
        last_error = response.error_message
        delay_ms = policy.base_delay_ms * (2 ** (attempt - 1))

        if callbacks and callbacks.on_retry_scheduled:
            await callbacks.on_retry_scheduled(
                attempt, max_attempts, delay_ms, last_error
            )

        await _sleep_ms(delay_ms, signal)

        if callbacks and callbacks.on_retry_attempt_start:
            await callbacks.on_retry_attempt_start()


def _parse_delay(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(str(value).strip()))
    except ValueError:
        return None


def realm_request_delay_ms(
    headers: _HeaderLike,
    retry_index: int,
    max_retry_delay_ms: float | None = None,
) -> float:
    """Delay before the next HTTP attempt.

    A Realm-supplied `Retry-After` wins. Anything longer than the cap raises
    rather than stalling the run; pass `max_retry_delay_ms=0` to disable it.
    Otherwise backoff is exponential, capped, and jittered downward so parallel
    callers do not retry in lockstep.
    """
    cap = (
        DEFAULT_MAX_RETRY_DELAY_MS if max_retry_delay_ms is None else max_retry_delay_ms
    )

    requested = _parse_delay(headers.get("retry-after-ms"))
    if requested is None:
        seconds = _parse_delay(headers.get("retry-after"))
        requested = None if seconds is None else seconds * 1000

    if requested is not None:
        if cap > 0 and requested > cap:
            raise ServerRetryDelayTooLongError(requested, cap)
        return float(requested)

    exponential = min(_BACKOFF_BASE_MS * (2**retry_index), _MAX_BACKOFF_MS)
    return float(exponential * (1 - random.random() * _JITTER_FRACTION))


def is_retryable_status(status: int, headers: _HeaderLike | None = None) -> bool:
    """Whether an HTTP status from a Realm is worth retrying.

    An explicit `x-should-retry` header from the Realm overrides the status.
    """
    if headers is not None:
        should_retry = headers.get("x-should-retry")
        if should_retry == "true":
            return True
        if should_retry == "false":
            return False
    return status in _RETRYABLE_STATUSES or status >= 500


def _status_of(error: Exception) -> int | None:
    status = getattr(error, "status", None)
    return status if isinstance(status, int) else None


def _headers_of(error: Exception) -> _HeaderLike | None:
    headers = getattr(error, "headers", None)
    return headers if headers is not None and hasattr(headers, "get") else None


def _is_retryable_request_error(error: Exception) -> bool:
    headers = _headers_of(error)
    if headers is not None:
        should_retry = headers.get("x-should-retry")
        if should_retry == "true":
            return True
        if should_retry == "false":
            return False

    status = _status_of(error)
    if status is None:
        return False
    return is_retryable_status(status)


async def retry_realm_request[T](
    request: Callable[[], Awaitable[T]],
    max_retries: int = 0,
    max_retry_delay_ms: float | None = None,
    signal: Any | None = None,
) -> T:
    """Run one HTTP request against a Realm, retrying transient failures."""
    remaining = max_retries

    while True:
        if signal is not None and signal.aborted:
            raise AbortError("Operation aborted")
        try:
            return await request()
        except Exception as error:
            if remaining <= 0 or not _is_retryable_request_error(error):
                raise
            retry_index = max_retries - remaining
            remaining -= 1
            headers = _headers_of(error)
            delay_ms = realm_request_delay_ms(
                headers if headers is not None else _EMPTY_HEADERS,
                retry_index,
                max_retry_delay_ms,
            )
            await _sleep_ms(delay_ms, signal)


class _EmptyHeaders:
    def get(self, key: str, default: Any = None) -> Any:
        return default


_EMPTY_HEADERS = _EmptyHeaders()


__all__ = [
    "DEFAULT_MAX_RETRY_DELAY_MS",
    "DEFAULT_RETRY_POLICY",
    "RetryCallbacks",
    "RetryPolicy",
    "ServerRetryDelayTooLongError",
    "is_retryable_realm_response",
    "is_retryable_status",
    "realm_request_delay_ms",
    "retry_invocation",
    "retry_realm_request",
]
