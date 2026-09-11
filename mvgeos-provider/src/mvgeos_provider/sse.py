from __future__ import annotations

import contextlib
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from mvgeos_provider.base import Realm
from mvgeos_provider.retry import (
    ServerRetryDelayTooLongError,
    _sleep_ms,
    is_retryable_realm_response,
    is_retryable_status,
    realm_request_delay_ms,
)
from mvgeos_provider.types import (
    AbortError,
    AbortSignal,
    ChannelConfig,
    Model,
    MvgeResponse,
    RealmResponse,
    StopReason,
)


@dataclass
class ParsedError:
    """Structured error extracted from an HTTP response or SSE error chunk."""

    message: str
    error_code: str | None = None
    retry_after: float | None = None
    limit_source: str | None = None
    remedy_hint: str | None = None
    reset_at: float | None = None
    quota_limit: int | None = None
    quota_remaining: int | None = None

    def __iter__(self) -> Any:
        return iter((self.message, self.error_code))

    def to_response(self, model: Model) -> RealmResponse:
        return RealmResponse(
            model=model,
            error_message=self.message,
            error_code=self.error_code,
            retry_after=self.retry_after,
            limit_source=self.limit_source,
            remedy_hint=self.remedy_hint,
            reset_at=self.reset_at,
            quota_limit=self.quota_limit,
            quota_remaining=self.quota_remaining,
        )


@dataclass
class SSEChunk:
    """Parsed Server-Sent Events delta or chunk."""

    content: str | None = None
    contemplation: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


logger = logging.getLogger(__name__)

_ERROR_LOG_BODY_CAP = 4000


def _get_header(
    headers: dict[str, Any] | Any,
    key: str,
    fallback: dict[str, Any] | None = None,
) -> str | None:
    for k in (key, key.lower(), key.title(), key.upper()):
        if headers and k in headers:
            return str(headers[k])
    if fallback:
        for k in (key, key.lower(), key.title(), key.upper()):
            if k in fallback:
                return str(fallback[k])
    return None


def _parse_rate_limits(
    headers: dict[str, Any] | Any,
    fallback_headers: dict[str, Any] | None = None,
) -> tuple[int | None, int | None, float | None]:
    quota_limit: int | None = None
    quota_remaining: int | None = None
    reset_at: float | None = None

    q_lim = _get_header(headers, "x-ratelimit-limit", fallback_headers)
    if q_lim is not None:
        with contextlib.suppress(Exception):
            quota_limit = int(float(q_lim))

    q_rem = _get_header(headers, "x-ratelimit-remaining", fallback_headers)
    if q_rem is not None:
        with contextlib.suppress(Exception):
            quota_remaining = int(float(q_rem))

    q_reset = _get_header(headers, "x-ratelimit-reset", fallback_headers)
    if q_reset is not None:
        with contextlib.suppress(Exception):
            val_f = float(q_reset)
            reset_at = val_f / 1000.0 if val_f > 1e11 else val_f

    return quota_limit, quota_remaining, reset_at


def _build_parsed_error(body: bytes, status_code: int, headers: Any) -> ParsedError:
    """Parse an HTTP error body into a ParsedError (pure, no I/O)."""
    try:
        error_data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        error_data = {}
    err_obj = error_data.get("error", {}) if isinstance(error_data, dict) else {}
    if not isinstance(err_obj, dict):
        err_obj = {"message": str(err_obj)} if err_obj else {}
    message = err_obj.get("message", f"HTTP {status_code}")
    if message:
        message = message.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if status_code == 429:
        error_code = "rate_limited"
        if message == f"HTTP {status_code}":
            message = "Rate limit exceeded"
    elif status_code == 401:
        error_code = "auth_failed"
    else:
        error_code = None

    err_dict = err_obj if isinstance(err_obj, dict) else {}
    metadata = err_dict.get("metadata", {}) if isinstance(err_dict, dict) else {}
    limit_source = metadata.get("limit_source") if isinstance(metadata, dict) else None
    remedy_hint = metadata.get("remedy_hint") if isinstance(metadata, dict) else None
    meta_headers = metadata.get("headers", {}) if isinstance(metadata, dict) else {}
    resp_headers = headers or {}

    quota_limit, quota_remaining, reset_at = _parse_rate_limits(
        resp_headers, meta_headers
    )

    retry_after: float | None = None
    q_retry = _get_header(resp_headers, "retry-after", meta_headers)
    if q_retry is not None:
        with contextlib.suppress(Exception):
            retry_after = float(q_retry)

    return ParsedError(
        message=message,
        error_code=error_code,
        retry_after=retry_after,
        limit_source=limit_source,
        remedy_hint=remedy_hint,
        reset_at=reset_at,
        quota_limit=quota_limit,
        quota_remaining=quota_remaining,
    )


def _error_from_response(response: Any) -> ParsedError:
    """Extract error message, error code, and diagnostics from an HTTP response."""
    try:
        body = response.read()
    except Exception:
        body = b""
    return _build_parsed_error(
        body, response.status_code, getattr(response, "headers", {})
    )


async def _error_from_response_async(
    response: Any, attempt: int = 0, max_attempts: int = 1
) -> ParsedError:
    """Async variant for streaming responses; falls back to sync read().

    Logs at DEBUG for intermediate retry attempts, WARNING for the final attempt.
    """
    body = b""
    try:
        aread = getattr(response, "aread", None)
        if callable(aread):
            body = await aread()
        else:
            body = response.read()
    except Exception:
        body = b""
    parsed = _build_parsed_error(
        body, response.status_code, getattr(response, "headers", {})
    )
    is_final = attempt >= max_attempts - 1
    log_level = logging.WARNING if is_final else logging.DEBUG
    attempt_str = f"attempt {attempt + 1}/{max_attempts}"
    if parsed.message == f"HTTP {response.status_code}":
        logger.log(
            log_level,
            "Realm request %s failed with status %s and unreadable body",
            attempt_str,
            response.status_code,
        )
    else:
        snippet = parsed.message[:_ERROR_LOG_BODY_CAP]
        logger.log(
            log_level,
            "Realm request %s failed (%s): %s",
            attempt_str,
            response.status_code,
            snippet,
        )
    return parsed


class SSEStreamingRealm(Realm, ABC):
    """Abstract base class for Realms that stream completions over SSE."""

    realm_name: str = ""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )

    @abstractmethod
    def _prepare_request(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Construct the request URL, headers, and JSON body."""
        raise NotImplementedError

    @abstractmethod
    def _parse_sse_chunk(self, chunk: dict[str, Any]) -> SSEChunk | None:
        """Parse a decoded SSE JSON chunk into an SSEChunk delta."""
        raise NotImplementedError

    def _parse_usage(self, usage: dict[str, Any]) -> dict[str, float]:
        """Convert a provider usage payload into a standard Mana breakdown."""
        if not usage:
            return {}
        prompt = float(usage.get("prompt_tokens", 0))
        completion = float(usage.get("completion_tokens", 0))
        total = float(usage.get("total_tokens", prompt + completion))
        breakdown: dict[str, float] = {
            "input": prompt,
            "output": completion,
            "total": total,
        }
        reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
        if reasoning:
            breakdown["contemplation"] = float(reasoning)
        return breakdown

    def _parse_error(self, response: Any) -> ParsedError:
        """Extract error message and code from a non-200 HTTP response."""
        return _error_from_response(response)

    async def _parse_error_async(
        self, response: Any, attempt: int = 0, max_attempts: int = 1
    ) -> ParsedError:
        """Async variant for streaming responses (uses aread with fallback)."""
        return await _error_from_response_async(response, attempt, max_attempts)

    def _realm_name(self, model: Model) -> str:
        """Derive the realm identifier to tag on MvgeResponse instances."""
        return self.realm_name or model.realm or "sse"

    async def stream(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
        signal: AbortSignal | None = None,
    ) -> AsyncIterator[RealmResponse]:
        url, headers, payload = self._prepare_request(model, invocations, config)
        max_attempts = max(1, config.max_retries)

        for attempt in range(max_attempts):
            if signal is not None and signal.aborted:
                raise AbortError("Operation aborted")

            async with self._client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=config.timeout_ms / 1000,
            ) as response:
                try:
                    retryable_chunk_error: RealmResponse | None = None
                    parsed_err: ParsedError | None = None
                    if response.status_code == 200:
                        streamed_any = False
                        async for item in self._consume_stream(model, response):
                            if signal is not None and signal.aborted:
                                raise AbortError("Operation aborted")
                            if (
                                item.error_message
                                and not streamed_any
                                and is_retryable_realm_response(item)
                                and attempt < max_attempts - 1
                            ):
                                retryable_chunk_error = item
                                break
                            streamed_any = True
                            yield item
                        if retryable_chunk_error is None:
                            return
                        message = retryable_chunk_error.error_message or ""
                        error_code = retryable_chunk_error.error_code
                    else:
                        parsed_err = await self._parse_error_async(
                            response, attempt, max_attempts
                        )
                        message, error_code = parsed_err
                        if not is_retryable_status(
                            response.status_code, response.headers
                        ):
                            yield parsed_err.to_response(model)
                            return
                finally:
                    if signal is not None and signal.aborted:
                        await response.aclose()

                if attempt >= max_attempts - 1:
                    if parsed_err is not None:
                        yield parsed_err.to_response(model)
                    else:
                        yield RealmResponse(
                            model=model,
                            error_message=message,
                            error_code=error_code,
                        )
                    return

                try:
                    delay_ms = realm_request_delay_ms(response.headers, attempt)
                except ServerRetryDelayTooLongError as exc:
                    yield RealmResponse(
                        model=model,
                        error_message=f"{exc}. {message}",
                        error_code=error_code,
                    )
                    return

            await _sleep_ms(delay_ms, signal)

    async def _consume_stream(
        self,
        model: Model,
        response: Any,
    ) -> AsyncIterator[RealmResponse]:
        text_parts: list[str] = []
        contemplation_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage_acc: dict[str, Any] = {}
        finished: bool = False

        async for line in response.aiter_lines():
            if not line:
                continue
            line_str = line if isinstance(line, str) else line.decode("utf-8")
            if not line_str.startswith("data:"):
                continue
            data = line_str[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            if isinstance(chunk, dict) and chunk.get("error"):
                err = chunk["error"]
                err_msg = (
                    err.get("message", "Stream error")
                    if isinstance(err, dict)
                    else str(err)
                )
                err_code = err.get("code") if isinstance(err, dict) else None
                meta = err.get("metadata", {}) if isinstance(err, dict) else {}
                meta_hdrs = meta.get("headers", {}) if isinstance(meta, dict) else {}
                quota_limit, quota_remaining, reset_at = _parse_rate_limits(meta_hdrs)

                yield RealmResponse(
                    model=model,
                    error_message=err_msg,
                    error_code=str(err_code) if err_code is not None else None,
                    limit_source=(
                        meta.get("limit_source") if isinstance(meta, dict) else None
                    ),
                    remedy_hint=(
                        meta.get("remedy_hint") if isinstance(meta, dict) else None
                    ),
                    quota_limit=quota_limit,
                    quota_remaining=quota_remaining,
                    reset_at=reset_at,
                )
                return

            parsed = self._parse_sse_chunk(chunk)
            if parsed is None:
                continue

            if parsed.usage:
                usage_acc = parsed.usage

            if parsed.contemplation:
                contemplation_parts.append(parsed.contemplation)
                yield RealmResponse(
                    model=model,
                    invocation=MvgeResponse(
                        role="assistant",
                        content=[
                            {"type": "contemplation", "text": parsed.contemplation}
                        ],
                        realm=self._realm_name(model),
                        model=model.id,
                    ),
                    stop_reason="pending",
                )

            if parsed.content:
                text_parts.append(parsed.content)
                yield RealmResponse(
                    model=model,
                    invocation=MvgeResponse(
                        role="assistant",
                        content=[{"type": "text", "text": parsed.content}],
                        realm=self._realm_name(model),
                        model=model.id,
                    ),
                    stop_reason="pending",
                )

            for tc in parsed.tool_calls or []:
                index = tc.get("index", 0)
                acc = tool_calls_acc.setdefault(
                    index, {"id": "", "name": "", "arguments": ""}
                )
                if tc.get("id"):
                    acc["id"] = tc["id"]
                func = tc.get("function", {})
                if func.get("name"):
                    acc["name"] = func["name"]
                if func.get("arguments"):
                    acc["arguments"] += func["arguments"]

            if parsed.finish_reason:
                finished = True
                yield self._build_final_response(
                    model=model,
                    text_parts=text_parts,
                    contemplation_parts=contemplation_parts,
                    tool_calls_acc=tool_calls_acc,
                    finish_reason=parsed.finish_reason,
                    usage=parsed.usage or usage_acc,
                )
                return

        if not finished and (text_parts or contemplation_parts or tool_calls_acc):
            yield self._build_final_response(
                model=model,
                text_parts=text_parts,
                contemplation_parts=contemplation_parts,
                tool_calls_acc=tool_calls_acc,
                finish_reason="stop",
                usage=usage_acc,
            )

    def _build_final_response(
        self,
        model: Model,
        text_parts: list[str],
        contemplation_parts: list[str],
        tool_calls_acc: dict[int, dict[str, Any]],
        finish_reason: str,
        usage: dict[str, Any],
    ) -> RealmResponse:
        blocks: list[dict[str, Any]] = []
        if contemplation_parts:
            blocks.append(
                {
                    "type": "contemplation",
                    "text": "".join(contemplation_parts),
                }
            )
        if text_parts:
            blocks.append({"type": "text", "text": "".join(text_parts)})

        for index in sorted(tool_calls_acc):
            acc = tool_calls_acc[index]
            try:
                arguments = json.loads(acc["arguments"]) if acc["arguments"] else {}
            except json.JSONDecodeError:
                arguments = {}
            blocks.append(
                {
                    "type": "spell_cast",
                    "spell_cast": {
                        "id": acc["id"],
                        "name": acc["name"],
                        "arguments": arguments,
                    },
                }
            )

        if tool_calls_acc:
            stop_reason = StopReason.SPELL_USE
        elif finish_reason == "length":
            stop_reason = StopReason.LENGTH
        else:
            stop_reason = StopReason.STOP

        mana_usage = self._parse_usage(usage)
        total_tokens = int(mana_usage.get("total", usage.get("total_tokens", 0)))

        invocation = MvgeResponse(
            role="assistant",
            content=blocks,
            realm=self._realm_name(model),
            model=model.id,
            stop_reason=stop_reason,
            mana_usage=mana_usage,
        )
        return RealmResponse(
            model=model,
            invocation=invocation,
            mana_used=total_tokens,
            stop_reason=stop_reason.value,
        )

    async def close(self) -> None:
        if (
            self._owned_client
            and self._client is not None
            and not self._client.is_closed
        ):
            await self._client.aclose()


__all__ = [
    "ParsedError",
    "SSEChunk",
    "SSEStreamingRealm",
    "_build_parsed_error",
    "_error_from_response",
    "_error_from_response_async",
]
