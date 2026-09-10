from __future__ import annotations

from typing import Any

import pytest

from mvgeos_provider.retry import (
    DEFAULT_MAX_RETRY_DELAY_MS,
    DEFAULT_RETRY_POLICY,
    RetryCallbacks,
    RetryPolicy,
    ServerRetryDelayTooLongError,
    is_retryable_realm_response,
    is_retryable_status,
    realm_request_delay_ms,
    retry_invocation,
    retry_realm_request,
)
from mvgeos_provider.types import Model, RealmResponse


def _model() -> Model:
    return Model(
        id="test-model",
        name="Test",
        realm="test",
        base_url="",
        api_key="",
    )


def _error(message: str, code: str | None = None) -> RealmResponse:
    return RealmResponse(
        model=_model(),
        error_message=message,
        error_code=code,
        stop_reason="error",
    )


def _ok() -> RealmResponse:
    return RealmResponse(model=_model(), stop_reason="stop")


class _Headers:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


class TestRetryPolicy:
    def test_defaults(self) -> None:
        assert DEFAULT_RETRY_POLICY.enabled is True
        assert DEFAULT_RETRY_POLICY.max_retries > 0
        assert DEFAULT_RETRY_POLICY.base_delay_ms > 0

    def test_disabled_policy_is_expressible(self) -> None:
        policy = RetryPolicy(enabled=False)
        assert policy.enabled is False


class TestClassifier:
    def test_non_error_is_not_retryable(self) -> None:
        assert is_retryable_realm_response(_ok()) is False

    def test_error_code_rate_limited_is_retryable(self) -> None:
        assert is_retryable_realm_response(_error("slow down", "rate_limited")) is True

    def test_error_code_auth_failed_is_not_retryable(self) -> None:
        assert is_retryable_realm_response(_error("nope", "auth_failed")) is False

    @pytest.mark.parametrize(
        "message",
        [
            "Provider returned error",
            "service unavailable",
            "connection refused",
            "socket hang up",
            "request timed out",
            "overloaded",
            "too many requests",
            "ResourceExhausted",
        ],
    )
    def test_transient_prose_is_retryable(self, message: str) -> None:
        assert is_retryable_realm_response(_error(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "insufficient_quota",
            "quota exceeded",
            "out of budget",
            "billing problem",
            "Monthly usage limit reached",
        ],
    )
    def test_quota_errors_are_not_retryable(self, message: str) -> None:
        assert is_retryable_realm_response(_error(message)) is False

    def test_quota_wins_over_transient_wording(self) -> None:
        # "429" reads as transient, but a quota limit is deterministic.
        assert is_retryable_realm_response(_error("429 quota exceeded")) is False

    def test_unknown_error_is_not_retryable(self) -> None:
        assert is_retryable_realm_response(_error("banana")) is False

    def test_empty_error_message_is_not_retryable(self) -> None:
        assert is_retryable_realm_response(_error("")) is False


class TestRetryInvocation:
    @pytest.mark.asyncio
    async def test_returns_first_success_without_retrying(self) -> None:
        calls = 0

        async def produce() -> RealmResponse:
            nonlocal calls
            calls += 1
            return _ok()

        result = await retry_invocation(produce, DEFAULT_RETRY_POLICY)

        assert calls == 1
        assert result.stop_reason == "stop"

    @pytest.mark.asyncio
    async def test_retries_transient_error_then_succeeds(self) -> None:
        calls = 0

        async def produce() -> RealmResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return _error("overloaded")
            return _ok()

        policy = RetryPolicy(max_retries=3, base_delay_ms=0)
        result = await retry_invocation(produce, policy)

        assert calls == 2
        assert result.stop_reason == "stop"

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_error(self) -> None:
        calls = 0

        async def produce() -> RealmResponse:
            nonlocal calls
            calls += 1
            return _error("insufficient_quota")

        policy = RetryPolicy(max_retries=5, base_delay_ms=0)
        result = await retry_invocation(produce, policy)

        assert calls == 1
        assert result.error_message == "insufficient_quota"

    @pytest.mark.asyncio
    async def test_stops_after_max_retries(self) -> None:
        calls = 0

        async def produce() -> RealmResponse:
            nonlocal calls
            calls += 1
            return _error("overloaded")

        policy = RetryPolicy(max_retries=2, base_delay_ms=0)
        result = await retry_invocation(produce, policy)

        assert calls == 3  # initial call plus two retries
        assert result.error_message == "overloaded"

    @pytest.mark.asyncio
    async def test_disabled_policy_never_retries(self) -> None:
        calls = 0

        async def produce() -> RealmResponse:
            nonlocal calls
            calls += 1
            return _error("overloaded")

        await retry_invocation(produce, RetryPolicy(enabled=False))

        assert calls == 1

    @pytest.mark.asyncio
    async def test_emits_callbacks_around_retry(self) -> None:
        scheduled: list[tuple[int, int, float, str]] = []
        started = 0
        finished: list[tuple[bool, int, str | None]] = []

        async def on_scheduled(
            attempt: int, max_attempts: int, delay_ms: float, message: str
        ) -> None:
            scheduled.append((attempt, max_attempts, delay_ms, message))

        async def on_start() -> None:
            nonlocal started
            started += 1

        async def on_finished(
            success: bool, attempt: int, final_error: str | None
        ) -> None:
            finished.append((success, attempt, final_error))

        calls = 0

        async def produce() -> RealmResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return _error("overloaded")
            return _ok()

        await retry_invocation(
            produce,
            RetryPolicy(max_retries=2, base_delay_ms=0),
            callbacks=RetryCallbacks(
                on_retry_scheduled=on_scheduled,
                on_retry_attempt_start=on_start,
                on_retry_finished=on_finished,
            ),
        )

        assert len(scheduled) == 1
        assert scheduled[0][0] == 1
        assert started == 1
        assert finished == [(True, 1, None)]

    @pytest.mark.asyncio
    async def test_no_callbacks_when_first_call_succeeds(self) -> None:
        finished: list[Any] = []

        async def on_finished(
            success: bool, attempt: int, final_error: str | None
        ) -> None:
            finished.append(success)

        async def produce() -> RealmResponse:
            return _ok()

        await retry_invocation(
            produce,
            DEFAULT_RETRY_POLICY,
            callbacks=RetryCallbacks(on_retry_finished=on_finished),
        )

        assert finished == []

    @pytest.mark.asyncio
    async def test_backoff_doubles_per_attempt(self) -> None:
        delays: list[float] = []

        async def on_scheduled(
            attempt: int, max_attempts: int, delay_ms: float, message: str
        ) -> None:
            delays.append(delay_ms)

        async def produce() -> RealmResponse:
            return _error("overloaded")

        await retry_invocation(
            produce,
            RetryPolicy(max_retries=3, base_delay_ms=100),
            callbacks=RetryCallbacks(on_retry_scheduled=on_scheduled),
        )

        assert delays == [100, 200, 400]


class TestIsRetryableStatus:
    @pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 524])
    def test_transient_statuses_retry(self, status: int) -> None:
        assert is_retryable_status(status, _Headers()) is True

    @pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 422])
    def test_client_errors_do_not_retry(self, status: int) -> None:
        assert is_retryable_status(status, _Headers()) is False

    def test_x_should_retry_true_overrides_status(self) -> None:
        headers = _Headers({"x-should-retry": "true"})
        assert is_retryable_status(400, headers) is True

    def test_x_should_retry_false_overrides_status(self) -> None:
        headers = _Headers({"x-should-retry": "false"})
        assert is_retryable_status(503, headers) is False


class TestRealmRequestDelay:
    def test_honours_retry_after_ms_header(self) -> None:
        headers = _Headers({"retry-after-ms": "2500"})
        assert realm_request_delay_ms(headers, 0) == 2500

    def test_honours_retry_after_seconds_header(self) -> None:
        headers = _Headers({"retry-after": "3"})
        assert realm_request_delay_ms(headers, 0) == 3000

    def test_rejects_server_delay_beyond_cap(self) -> None:
        headers = _Headers({"retry-after": "120"})
        with pytest.raises(ServerRetryDelayTooLongError):
            realm_request_delay_ms(headers, 0)

    def test_allows_long_delay_when_cap_disabled(self) -> None:
        headers = _Headers({"retry-after": "120"})
        assert realm_request_delay_ms(headers, 0, max_retry_delay_ms=0) == 120_000

    def test_exponential_backoff_is_capped_at_eight_seconds(self) -> None:
        headers = _Headers()
        for index in range(10):
            assert realm_request_delay_ms(headers, index) <= 8000

    def test_exponential_backoff_applies_jitter(self) -> None:
        headers = _Headers()
        # 0.5 * 2^3 = 4s, jitter keeps it within (0.75 * 4000, 4000]
        delays = {realm_request_delay_ms(headers, 3) for _ in range(50)}
        assert all(3000 <= delay <= 4000 for delay in delays)
        assert len(delays) > 1  # jitter actually varies

    def test_default_cap_is_sixty_seconds(self) -> None:
        assert DEFAULT_MAX_RETRY_DELAY_MS == 60_000


class TestRetryRealmRequest:
    @pytest.mark.asyncio
    async def test_returns_first_success(self) -> None:
        calls = 0

        async def request() -> str:
            nonlocal calls
            calls += 1
            return "ok"

        assert await retry_realm_request(request, max_retries=3) == "ok"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_retries_retryable_status(self) -> None:
        calls = 0

        async def request() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _status_error(503)
            return "ok"

        assert await retry_realm_request(request, max_retries=2) == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_status(self) -> None:
        calls = 0

        async def request() -> str:
            nonlocal calls
            calls += 1
            raise _status_error(400)

        with pytest.raises(_StatusError):
            await retry_realm_request(request, max_retries=3)
        assert calls == 1

    @pytest.mark.asyncio
    async def test_x_should_retry_header_forces_retry(self) -> None:
        calls = 0

        async def request() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _status_error(400, {"x-should-retry": "true"})
            return "ok"

        assert await retry_realm_request(request, max_retries=2) == "ok"
        assert calls == 2

    @pytest.mark.asyncio
    async def test_x_should_retry_false_blocks_retry(self) -> None:
        calls = 0

        async def request() -> str:
            nonlocal calls
            calls += 1
            raise _status_error(503, {"x-should-retry": "false"})

        with pytest.raises(_StatusError):
            await retry_realm_request(request, max_retries=3)
        assert calls == 1

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self) -> None:
        calls = 0

        async def request() -> str:
            nonlocal calls
            calls += 1
            raise _status_error(500)

        with pytest.raises(_StatusError):
            await retry_realm_request(request, max_retries=2)
        assert calls == 3

    @pytest.mark.asyncio
    async def test_retry_invocation_aborted_before_start(self) -> None:
        from mvgeos_provider.types import AbortController, AbortError

        controller = AbortController()
        controller.abort()

        async def produce() -> RealmResponse:
            return _error("transient")

        with pytest.raises(AbortError):
            await retry_invocation(produce, signal=controller.signal)

    @pytest.mark.asyncio
    async def test_retry_invocation_aborted_during_sleep(self) -> None:
        import asyncio

        from mvgeos_provider.types import AbortController, AbortError

        controller = AbortController()

        async def produce() -> RealmResponse:
            return _error("overloaded")

        policy = RetryPolicy(max_retries=3, base_delay_ms=2000)

        async def abort_soon() -> None:
            await asyncio.sleep(0.05)
            controller.abort()

        asyncio.create_task(abort_soon())

        with pytest.raises(AbortError):
            await retry_invocation(produce, policy=policy, signal=controller.signal)

    def test_parse_delay_invalid_returns_none(self) -> None:
        from mvgeos_provider.retry import _parse_delay

        assert _parse_delay("not-a-number") is None
        assert _parse_delay(None) is None
        assert _parse_delay(" 12.5 ") == 12.5


class _StatusError(Exception):
    def __init__(self, status: int, headers: _Headers) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.headers = headers


def _status_error(status: int, headers: dict[str, str] | None = None) -> _StatusError:
    return _StatusError(status, _Headers(headers))
