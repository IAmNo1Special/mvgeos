from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from mvgeos_provider.base import Realm
from mvgeos_provider.retry import (
    ServerRetryDelayTooLongError,
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
class SSEChunk:
    """Parsed Server-Sent Events delta or chunk."""

    content: str | None = None
    contemplation: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


async def _sleep_with_signal(delay_seconds: float, signal: AbortSignal | None) -> None:
    """Sleep for delay_seconds, but abort early if signal is aborted."""
    if signal is None:
        await asyncio.sleep(delay_seconds)
        return

    if signal.aborted:
        raise AbortError("Operation aborted")

    task = asyncio.ensure_future(asyncio.sleep(delay_seconds))

    def _on_abort() -> None:
        if not task.done():
            task.cancel()

    signal.on_abort(_on_abort)
    try:
        await task
    except asyncio.CancelledError:
        if signal.aborted:
            raise AbortError("Operation aborted") from None
        raise


def _error_from_response(response: Any) -> tuple[str, str | None]:
    """Extract human-readable error message and error code from an HTTP response."""
    try:
        body = response.read()
        error_data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        error_data = {}
    message = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
    if message:
        message = message.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if response.status_code == 429:
        error_code = "rate_limited"
        if message == f"HTTP {response.status_code}":
            message = "Rate limit exceeded"
    elif response.status_code == 401:
        error_code = "auth_failed"
    else:
        error_code = None
    return message, error_code


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

    def _parse_error(self, response: Any) -> tuple[str, str | None]:
        """Extract error message and code from a non-200 HTTP response."""
        return _error_from_response(response)

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
                    if response.status_code == 200:
                        async for item in self._consume_stream(model, response):
                            if signal is not None and signal.aborted:
                                raise AbortError("Operation aborted")
                            yield item
                        return

                    message, error_code = self._parse_error(response)
                    if not is_retryable_status(response.status_code, response.headers):
                        yield RealmResponse(
                            model=model, error_message=message, error_code=error_code
                        )
                        return
                finally:
                    if signal is not None and signal.aborted:
                        await response.aclose()

                if attempt >= max_attempts - 1:
                    yield RealmResponse(
                        model=model, error_message=message, error_code=error_code
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

            try:
                await _sleep_with_signal(delay_ms / 1000, signal)
            except AbortError:
                raise
            except asyncio.CancelledError:
                if signal is not None and signal.aborted:
                    raise AbortError("Operation aborted") from None
                raise

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
    "SSEChunk",
    "SSEStreamingRealm",
]
