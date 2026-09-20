from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mvgeos_core.abort import (
    AbortController,
    AbortError,
)
from mvgeos_core.channel import (
    ChannelConfig,
    Model,
    RealmResponse,
    StopReason,
)

from mvgeos_provider.sse import SSEChunk, SSEStreamingRealm


class MockStreamResponse:
    def __init__(
        self,
        lines: list[bytes],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> None:
        self._lines = lines
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body or b""
        self.aclose = AsyncMock()

    async def aiter_lines(self) -> AsyncIterator[bytes]:
        for line in self._lines:
            yield line

    def read(self) -> bytes:
        return self._body

    async def aread(self) -> bytes:
        return self._body


def _make_client(
    lines: list[bytes],
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    sink: dict[str, Any] | None = None,
) -> httpx.AsyncClient:
    class _MockStreamCM:
        def __init__(self, method: str, url: str, **kwargs: Any) -> None:
            if sink is not None:
                sink.update(kwargs)
                sink["method"] = method
                sink["url"] = url

        async def __aenter__(self) -> MockStreamResponse:
            return MockStreamResponse(
                lines=lines,
                status_code=status_code,
                headers=headers,
                body=body,
            )

        async def __aexit__(self, *args: Any) -> None:
            pass

    client = AsyncMock(spec=httpx.AsyncClient)
    client.stream = _MockStreamCM
    client.is_closed = False
    return client


def _make_sequence_client(
    entries: list[tuple[int, dict[str, str], list[bytes], bytes]],
) -> httpx.AsyncClient:
    class _SeqCM:
        _calls = 0

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> MockStreamResponse:
            idx = min(_SeqCM._calls, len(entries) - 1)
            _SeqCM._calls += 1
            status, headers, lines, body = entries[idx]
            return MockStreamResponse(
                lines=lines,
                status_code=status,
                headers=headers,
                body=body,
            )

        async def __aexit__(self, *args: Any) -> None:
            pass

    client = AsyncMock(spec=httpx.AsyncClient)
    client.stream = _SeqCM
    client.is_closed = False
    return client


class DummySSERealm(SSEStreamingRealm):
    def _prepare_request(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"{self._base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        }
        if config.tools:
            payload["tools"] = config.tools
        return url, headers, payload

    def _parse_sse_chunk(self, chunk: dict[str, Any]) -> SSEChunk | None:
        usage = chunk.get("usage")
        choices = chunk.get("choices") or []
        if not choices:
            if usage:
                return SSEChunk(usage=usage)
            return None

        choice = choices[0]
        delta = choice.get("delta", {})
        return SSEChunk(
            content=delta.get("content"),
            contemplation=delta.get("reasoning"),
            tool_calls=delta.get("tool_calls"),
            finish_reason=choice.get("finish_reason"),
            usage=usage,
        )


def _test_model() -> Model:
    return Model(
        id="test-provider/test-model",
        name="Test Model",
        realm="test-realm",
        base_url="https://api.example.com/v1",
        api_key="test-key",
    )


async def _collect(gen: AsyncIterator[RealmResponse]) -> list[RealmResponse]:
    return [item async for item in gen]


@pytest.mark.asyncio
async def test_stream_text_deltas_and_final_invocation() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 3
    # Two partial deltas
    assert responses[0].stop_reason == "pending"
    assert responses[0].invocation is not None
    assert responses[0].invocation.content == [{"type": "text", "text": "Hello"}]

    assert responses[1].stop_reason == "pending"
    assert responses[1].invocation is not None
    assert responses[1].invocation.content == [{"type": "text", "text": " world"}]

    # Final response
    assert responses[2].stop_reason == "stop"
    assert responses[2].invocation is not None
    assert responses[2].invocation.content == [{"type": "text", "text": "Hello world"}]
    assert responses[2].invocation.stop_reason == StopReason.STOP
    assert responses[2].invocation.realm == "test-realm"


@pytest.mark.asyncio
async def test_stream_contemplation_deltas() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"reasoning":"Thinking deep"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"Answer"}}]}\n\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 3
    assert responses[0].invocation is not None
    assert responses[0].invocation.content == [
        {"type": "contemplation", "text": "Thinking deep"}
    ]

    final = responses[-1]
    assert final.invocation is not None
    assert final.invocation.content == [
        {"type": "contemplation", "text": "Thinking deep"},
        {"type": "text", "text": "Answer"},
    ]


@pytest.mark.asyncio
async def test_stream_accumulates_tool_calls() -> None:
    lines = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
            b'"type":"function","function":{"name":"bash","arguments":"{\\"cmd\\":'
            b' \\"ls\\"}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    final = responses[0]
    assert final.stop_reason == StopReason.SPELL_USE.value
    assert final.invocation is not None
    assert final.invocation.stop_reason == StopReason.SPELL_USE
    assert final.invocation.content[0]["type"] == "spell_cast"
    spell_cast = final.invocation.content[0]["spell_cast"]
    assert spell_cast["id"] == "call_1"
    assert spell_cast["name"] == "bash"
    assert spell_cast["arguments"] == {"cmd": "ls"}


@pytest.mark.asyncio
async def test_stream_mana_usage_breakdown() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n',
        (
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":10,"completion_tokens":4,"total_tokens":14,'
            b'"completion_tokens_details":{"reasoning_tokens":2}}}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    final = responses[-1]
    assert final.mana_used == 14
    assert final.invocation is not None
    assert final.invocation.mana_usage == {
        "input": 10.0,
        "output": 4.0,
        "total": 14.0,
        "contemplation": 2.0,
    }


@pytest.mark.asyncio
async def test_stream_usage_chunk_after_finish_reason() -> None:
    """OpenRouter sends the usage chunk AFTER the finish_reason chunk.

    The final response must still carry the mana breakdown instead of
    dropping the usage that arrives after finish_reason.
    """
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
        (
            b'data: {"usage":{"prompt_tokens":10,"completion_tokens":4,'
            b'"total_tokens":14}}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    final = responses[-1]
    assert final.invocation is not None
    assert final.invocation.mana_usage == {
        "input": 10.0,
        "output": 4.0,
        "total": 14.0,
    }


@pytest.mark.asyncio
async def test_stream_requests_usage_in_stream_options() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    sink: dict[str, Any] = {}
    realm = DummySSERealm(client=_make_client(lines, sink=sink))
    model = _test_model()
    config = ChannelConfig(model=model)

    await _collect(realm.stream(model, [], config))

    payload = sink["json"]
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_stream_preserves_realm_stream_options() -> None:
    lines = [
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    class OptionsRealm(DummySSERealm):
        def _prepare_request(
            self,
            model: Model,
            invocations: list[Any],
            config: ChannelConfig,
        ) -> tuple[str, dict[str, str], dict[str, Any]]:
            url, headers, payload = super()._prepare_request(model, invocations, config)
            payload["stream_options"] = {"include_usage": False}
            return url, headers, payload

    sink: dict[str, Any] = {}
    realm = OptionsRealm(client=_make_client(lines, sink=sink))

    await _collect(realm.stream(_test_model(), [], ChannelConfig(model=_test_model())))

    assert sink["json"]["stream_options"] == {"include_usage": False}


@pytest.mark.asyncio
async def test_stream_handles_empty_choices_and_done() -> None:
    lines = [
        b'data: {"choices":[]}\n\n',
        b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
        (
            b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":1,'
            b'"total_tokens":4}}\n\n'
        ),
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 2
    final = responses[-1]
    assert final.mana_used == 4
    assert final.invocation is not None
    assert final.invocation.content == [{"type": "text", "text": "ok"}]


@pytest.mark.asyncio
async def test_stream_finish_reason_length_maps_to_length() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"truncated"}}]}\n\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    final = responses[-1]
    assert final.stop_reason == "length"
    assert final.invocation is not None
    assert final.invocation.stop_reason == StopReason.LENGTH


@pytest.mark.asyncio
async def test_stream_cancelled_before_request_raises_abort_error() -> None:
    realm = DummySSERealm()
    model = _test_model()
    config = ChannelConfig(model=model)

    controller = AbortController()
    controller.abort()

    with pytest.raises(AbortError, match="Operation aborted"):
        async for _ in realm.stream(model, [], config, signal=controller.signal):
            pass


@pytest.mark.asyncio
async def test_stream_cancelled_mid_stream_raises_abort_error() -> None:
    controller = AbortController()

    class AbortingStreamCM:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> MockStreamResponse:
            resp = MockStreamResponse(
                lines=[b'data: {"choices":[{"delta":{"content":"part1"}}]}\n\n']
            )

            async def aborting_iter() -> AsyncIterator[bytes]:
                yield b'data: {"choices":[{"delta":{"content":"part1"}}]}\n\n'
                controller.abort()
                yield b'data: {"choices":[{"delta":{"content":"part2"}}]}\n\n'

            resp.aiter_lines = aborting_iter  # type: ignore[method-assign]
            return resp

        async def __aexit__(self, *args: Any) -> None:
            pass

    client = AsyncMock(spec=httpx.AsyncClient)
    client.stream = AbortingStreamCM
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model)

    with pytest.raises(AbortError, match="Operation aborted"):
        await _collect(realm.stream(model, [], config, signal=controller.signal))


@pytest.mark.asyncio
async def test_stream_error_translation_401_auth_failed() -> None:
    client = _make_client(
        lines=[],
        status_code=401,
        body=b'{"error": {"message": "Invalid API key"}}',
    )
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    assert responses[0].error_code == "auth_failed"
    assert responses[0].error_message == "Invalid API key"


@pytest.mark.asyncio
async def test_stream_error_translation_429_rate_limited() -> None:
    client = _make_client(
        lines=[],
        status_code=429,
        body=b'{"error": {"message": "Rate limit exceeded"}}',
    )
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=1)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    assert responses[0].error_code == "rate_limited"
    assert responses[0].error_message == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_stream_retries_transient_503_then_succeeds() -> None:
    client = _make_sequence_client(
        [
            (503, {}, [], b'{"error":{"message":"Temporarily unavailable"}}'),
            (
                200,
                {},
                [
                    b'data: {"choices":[{"delta":{"content":"recovered"}}]}\n\n',
                    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
                    b"data: [DONE]\n\n",
                ],
                b"",
            ),
        ]
    )
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=3)

    with patch("asyncio.sleep", new=AsyncMock()):
        responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 2
    assert responses[-1].stop_reason == "stop"
    assert responses[-1].invocation is not None
    assert responses[-1].invocation.content == [{"type": "text", "text": "recovered"}]


@pytest.mark.asyncio
async def test_stream_server_retry_delay_too_long() -> None:
    client = _make_client(
        lines=[],
        status_code=429,
        headers={"retry-after": "300"},
        body=b'{"error":{"message":"Slow down"}}',
    )
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=2)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    assert responses[0].error_message is not None
    assert "retry delay" in responses[0].error_message


@pytest.mark.asyncio
async def test_close_realm() -> None:
    client = httpx.AsyncClient()
    realm = DummySSERealm(client=client)
    await realm.close()
    assert not client.is_closed
    await client.aclose()

    owned_realm = DummySSERealm()
    await owned_realm.close()


@pytest.mark.asyncio
async def test_stream_chunk_error_surfaces_realm_response() -> None:
    lines = [
        b'data: {"id":"gen-1","choices":[],"error":'
        b'{"code":400,"message":"Invalid tool name"}}\n\n',
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    assert responses[0].error_message == "Invalid tool name"
    assert responses[0].error_code == "400"


@pytest.mark.asyncio
async def test_stream_chunk_error_retryable_recovers() -> None:
    err_chunk = (
        b'data: {"error":{"code":503,"message":"Upstream error from Nvidia: '
        b'Service temporarily overloaded"}}\n\n'
    )
    rec_chunk = (
        b'data: {"choices":[{"delta":{"content":"recovered"},'
        b'"finish_reason":"stop"}]}\n\n'
    )
    entries = [
        (200, {}, [err_chunk], b""),
        (200, {}, [rec_chunk, b"data: [DONE]\n\n"], b""),
    ]
    client = _make_sequence_client(entries)
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=2)

    with patch("mvgeos_provider.sse.realm_request_delay_ms", return_value=0.0):
        responses = await _collect(realm.stream(model, [], config))

    assert len(responses) > 0
    assert any(
        r.invocation is not None
        and any(c.get("text") == "recovered" for c in r.invocation.content)
        for r in responses
    )


@pytest.mark.asyncio
async def test_stream_mid_stream_retryable_error_classified() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
        b'data: {"error":{"code":503,"message":"Upstream idle timeout exceeded"}}\n\n',
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=2)

    with patch("mvgeos_provider.sse.realm_request_delay_ms", return_value=0.0):
        responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 2
    assert responses[0].stop_reason == "pending"
    assert responses[1].error_message == "Upstream idle timeout exceeded"
    assert responses[1].error_code == "upstream_idle_timeout"


@pytest.mark.asyncio
async def test_stream_mid_stream_non_retryable_error_keeps_code() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
        b'data: {"id":"gen-1","choices":[],"error":'
        b'{"code":400,"message":"Invalid tool name"}}\n\n',
    ]
    realm = DummySSERealm(client=_make_client(lines))
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=2)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 2
    assert responses[1].error_message == "Invalid tool name"
    assert responses[1].error_code == "400"


@pytest.mark.asyncio
async def test_stream_chunk_error_retryable_exhausts_retries() -> None:
    err_chunk = (
        b'data: {"error":{"code":503,"message":"Upstream error from Nvidia: '
        b'Service temporarily overloaded"}}\n\n'
    )
    entries = [
        (200, {}, [err_chunk], b""),
        (200, {}, [err_chunk], b""),
    ]
    client = _make_sequence_client(entries)
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=2)

    with patch("mvgeos_provider.sse.realm_request_delay_ms", return_value=0.0):
        responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    assert "temporarily overloaded" in (responses[0].error_message or "")


def test_error_from_response_parses_openrouter_rate_limit_metadata() -> None:
    from mvgeos_provider.sse import _error_from_response

    class FakeResponse:
        status_code = 429
        headers = {
            "x-ratelimit-limit": "50",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "1788566400000",
            "retry-after": "60",
        }

        def read(self) -> bytes:
            body = {
                "error": {
                    "code": 429,
                    "message": "Rate limit exceeded: free-models-per-day.",
                    "metadata": {
                        "limit_source": "openrouter_free_tier_daily",
                        "remedy_hint": "Wait for daily reset or purchase credits.",
                    },
                }
            }
            return json.dumps(body).encode("utf-8")

    err = _error_from_response(FakeResponse())
    assert err.message == "Rate limit exceeded: free-models-per-day."
    assert err.error_code == "rate_limited"
    assert err.limit_source == "openrouter_free_tier_daily"
    assert err.remedy_hint == "Wait for daily reset or purchase credits."
    assert err.quota_limit == 50
    assert err.quota_remaining == 0
    assert err.reset_at == 1788566400.0
    assert err.retry_after == 60.0

    # Unpack as tuple
    msg, code = err
    assert msg == "Rate limit exceeded: free-models-per-day."
    assert code == "rate_limited"


@pytest.mark.asyncio
async def test_stream_exhausts_retries_surfaces_diagnostic_fields() -> None:
    err_body = json.dumps(
        {
            "error": {
                "code": 429,
                "message": "Rate limit exceeded: free-models-per-day.",
                "metadata": {
                    "limit_source": "openrouter_free_tier_daily",
                    "remedy_hint": "Add credits",
                },
            }
        }
    ).encode("utf-8")

    entries = [
        (429, {"x-ratelimit-limit": "50", "x-ratelimit-remaining": "0"}, [], err_body),
    ]
    client = _make_sequence_client(entries)
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=1)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    resp = responses[0]
    assert resp.error_code == "rate_limited"
    assert resp.limit_source == "openrouter_free_tier_daily"
    assert resp.remedy_hint == "Add credits"
    assert resp.quota_limit == 50
    assert resp.quota_remaining == 0


@pytest.mark.asyncio
async def test_error_from_response_async_uses_aread() -> None:
    from mvgeos_provider.sse import _error_from_response_async

    class AsyncOnlyResponse:
        status_code = 400
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            raise RuntimeError("sync read() in async streaming context")

        async def aread(self) -> bytes:
            return b'{"error": {"message": "context length exceeded"}}'

    err = await _error_from_response_async(AsyncOnlyResponse())
    assert err.message == "context length exceeded"


@pytest.mark.asyncio
async def test_error_from_response_async_falls_back_to_read() -> None:
    from mvgeos_provider.sse import _error_from_response_async

    class SyncOnlyResponse:
        status_code = 400
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            return b'{"error": {"message": "bad request"}}'

    err = await _error_from_response_async(SyncOnlyResponse())
    assert err.message == "bad request"


@pytest.mark.asyncio
async def test_error_from_response_async_unreadable_body() -> None:
    from mvgeos_provider.sse import _error_from_response_async

    class BrokenResponse:
        status_code = 400
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            raise RuntimeError("nope")

        async def aread(self) -> bytes:
            raise RuntimeError("nope")

    err = await _error_from_response_async(BrokenResponse())
    assert err.message == "HTTP 400"


@pytest.mark.asyncio
async def test_stream_400_surfaces_provider_message() -> None:
    client = _make_client(
        lines=[],
        status_code=400,
        body=b'{"error": {"message": "prompt is too long"}}',
    )
    realm = DummySSERealm(client=client)
    model = _test_model()
    config = ChannelConfig(model=model, max_retries=1)

    responses = await _collect(realm.stream(model, [], config))

    assert len(responses) == 1
    assert responses[0].error_message == "prompt is too long"


def test_error_from_response_string_error_body() -> None:
    from mvgeos_provider.sse import _error_from_response

    class StringErrorResponse:
        status_code = 400
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            return b'{"error": "boom"}'

    err = _error_from_response(StringErrorResponse())
    assert err.message == "boom"


@pytest.mark.asyncio
async def test_error_from_response_async_log_level_by_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify _error_from_response_async log level by attempt number."""
    import logging

    from mvgeos_provider.sse import _error_from_response_async

    class AsyncErrorResponse:
        status_code = 429
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            raise RuntimeError("sync read not available")

        async def aread(self) -> bytes:
            return b'{"error": {"message": "Rate limit exceeded"}}'

    # Test intermediate attempt (not final) -> DEBUG
    with caplog.at_level(logging.DEBUG, logger="mvgeos_provider.sse"):
        await _error_from_response_async(
            AsyncErrorResponse(), attempt=0, max_attempts=3
        )

    debug_logs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debug_logs) == 1
    assert "attempt 1/3" in debug_logs[0].message
    assert "Rate limit exceeded" in debug_logs[0].message

    # Clear caplog
    caplog.clear()

    # Test final attempt -> WARNING
    with caplog.at_level(logging.WARNING, logger="mvgeos_provider.sse"):
        await _error_from_response_async(
            AsyncErrorResponse(), attempt=2, max_attempts=3
        )

    warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_logs) == 1
    assert "attempt 3/3" in warning_logs[0].message
    assert "Rate limit exceeded" in warning_logs[0].message
