from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from mvgeos_agent.types import MvgeResponse, StopReason

from mvgeos_provider.base import Realm
from mvgeos_provider.retry import (
    ServerRetryDelayTooLongError,
    is_retryable_status,
    realm_request_delay_ms,
)
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse

_REASONING_MODELS = ("openai/o1", "openai/o3")


def _mana_usage(usage: dict[str, Any]) -> dict[str, float]:
    """Break a Realm usage block into the Mana figures compaction reads."""
    if not usage:
        return {}
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt + completion)
    breakdown: dict[str, float] = {
        "input": prompt,
        "output": completion,
        "total": total,
    }
    reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
    if reasoning:
        breakdown["contemplation"] = reasoning
    return breakdown


def _supports_reasoning(model: Model) -> bool:
    if model.supported_parameters:
        return "reasoning" in model.supported_parameters
    return any(m in model.id for m in _REASONING_MODELS)


def _error_from_response(response: Any) -> tuple[str, str | None]:
    content_type = response.headers.get("content-type", "")
    is_json = content_type.startswith("application/json")
    try:
        error_data = response.json() if is_json else {}
    except Exception:
        error_data = {}
    message = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
    if message:
        message = message.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if response.status_code == 429:
        error_code = "rate_limited"
        # Use a clean message for rate limits; the CLI shows a friendly template
        if message == f"HTTP {response.status_code}":
            message = "Rate limit exceeded"
    elif response.status_code == 401:
        error_code = "auth_failed"
    else:
        error_code = None
    return message, error_code


def _retry_after_seconds(response: Any) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        return None


def _invocations_to_messages(invocations: list[Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for inv in invocations:
        if hasattr(inv, "role") and inv.role == "user":
            messages.append({"role": "user", "content": inv.content or ""})
        elif hasattr(inv, "role") and inv.role == "assistant":
            if hasattr(inv, "content") and inv.content:
                text_parts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                for block in inv.content:
                    if block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                    elif block.get("type") == "tool_call":
                        tc = block.get("tool_call", {})
                        tool_calls.append(
                            {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(tc.get("arguments", {})),
                                },
                            }
                        )
                if tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "".join(text_parts) or None,
                            "tool_calls": tool_calls,
                        }
                    )
                else:
                    messages.append(
                        {"role": "assistant", "content": "".join(text_parts)}
                    )
        elif hasattr(inv, "role") and inv.role == "spellResult":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(inv, "spell_cast_id", ""),
                    "content": inv.content[0].get("text", "") if inv.content else "",
                }
            )
    return messages


class OpenRouterRealm(Realm):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url or "https://openrouter.ai/api/v1"
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

    def _prepare_request_url_and_headers(
        self, model: Model
    ) -> tuple[str, dict[str, str]]:
        base_url = (
            model.base_url or self._base_url or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        api_key = model.api_key or self._api_key
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if model.headers:
            headers.update(model.headers)
        return url, headers

    async def stream(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
    ) -> AsyncIterator[RealmResponse]:
        messages = _invocations_to_messages(invocations)
        url, headers = self._prepare_request_url_and_headers(model)

        payload = {
            "model": model.id,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
        }

        if _supports_reasoning(model) and not config.exclude_contemplation:
            reasoning: dict[str, Any] = {"effort": config.contemplation_level}
            if config.contemplation_budget is not None:
                reasoning["max_tokens"] = config.contemplation_budget
            payload["reasoning"] = reasoning

        if config.max_output_mana is not None:
            payload["max_tokens"] = min(config.max_tokens, config.max_output_mana)

        if config.tools:
            payload["tools"] = config.tools

        max_attempts = max(1, config.max_retries)
        for attempt in range(max_attempts):
            async with self._client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=config.timeout_ms / 1000,
            ) as response:
                if response.status_code == 200:
                    async for item in self._consume_stream(model, response):
                        yield item
                    return

                message, error_code = _error_from_response(response)
                if not is_retryable_status(response.status_code, response.headers):
                    yield RealmResponse(
                        model=model, error_message=message, error_code=error_code
                    )
                    return

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

            await asyncio.sleep(delay_ms / 1000)

    async def complete(
        self,
        model: Model,
        messages: list[dict[str, Any]],
        config: ChannelConfig,
    ) -> RealmResponse:
        """Run one non-channelled completion.

        Deliberately omits `tools`: this is used for standalone requests such
        as compaction summaries, where Spells must not be offered.
        """
        url, headers = self._prepare_request_url_and_headers(model)
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": messages,
            "stream": False,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        response = await self._client.post(
            url,
            headers=headers,
            json=payload,
            timeout=config.timeout_ms / 1000,
        )

        if response.status_code != 200:
            message, error_code = _error_from_response(response)
            return RealmResponse(
                model=model, error_message=message, error_code=error_code
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return RealmResponse(
                model=model,
                error_message="Realm returned no choices",
            )

        content = choices[0].get("message", {}).get("content") or ""
        usage = data.get("usage", {})
        return RealmResponse(
            model=model,
            invocation=MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": content}],
                realm="openrouter",
                model=model.id,
                stop_reason=StopReason.STOP,
                mana_usage=_mana_usage(usage),
            ),
            mana_used=usage.get("total_tokens", 0),
            stop_reason=StopReason.STOP.value,
        )

    async def _consume_stream(
        self,
        model: Model,
        response: Any,
    ) -> AsyncIterator[RealmResponse]:
        text_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}

        async for line in response.aiter_lines():
            if not line:
                continue
            line_str = line if isinstance(line, str) else line.decode("utf-8")
            if not line_str.startswith("data: "):
                continue
            data = line_str[6:]
            if data.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            choice = chunk.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")
            usage = chunk.get("usage", {})

            # Contemplation arrives as its own delta field. Surface it as a
            # distinct block so it never lands in the answer text.
            contemplation = delta.get("reasoning") or delta.get("reasoning_content")
            if contemplation:
                yield RealmResponse(
                    model=model,
                    invocation=MvgeResponse(
                        role="assistant",
                        content=[{"type": "contemplation", "text": contemplation}],
                        realm="openrouter",
                        model=model.id,
                    ),
                    stop_reason="pending",
                )

            content = delta.get("content")
            if content:
                text_parts.append(content)
                yield RealmResponse(
                    model=model,
                    invocation=MvgeResponse(
                        role="assistant",
                        content=[{"type": "text", "text": content}],
                        realm="openrouter",
                        model=model.id,
                    ),
                    stop_reason="pending",
                )

            for tc in delta.get("tool_calls") or []:
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

            if finish_reason:
                blocks: list[dict[str, Any]] = []
                if text_parts:
                    blocks.append({"type": "text", "text": "".join(text_parts)})
                for index in sorted(tool_calls_acc):
                    acc = tool_calls_acc[index]
                    try:
                        arguments = (
                            json.loads(acc["arguments"]) if acc["arguments"] else {}
                        )
                    except json.JSONDecodeError:
                        arguments = {}
                    blocks.append(
                        {
                            "type": "tool_call",
                            "tool_call": {
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

                invocation = MvgeResponse(
                    role="assistant",
                    content=blocks,
                    realm="openrouter",
                    model=model.id,
                    stop_reason=stop_reason,
                    mana_usage=_mana_usage(usage),
                )
                yield RealmResponse(
                    model=model,
                    invocation=invocation,
                    mana_used=usage.get("total_tokens", 0),
                    stop_reason=stop_reason.value,
                )
                return

    async def close(self) -> None:
        if (
            self._owned_client
            and self._client is not None
            and not self._client.is_closed
        ):
            await self._client.aclose()
