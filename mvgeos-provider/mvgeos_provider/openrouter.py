from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from mvgeos_provider.base import Realm
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse


def _invocations_to_messages(invocations: list[Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for inv in invocations:
        if hasattr(inv, "role") and inv.role == "user":
            messages.append({"role": "user", "content": inv.content or ""})
        elif hasattr(inv, "role") and inv.role == "assistant":
            if hasattr(inv, "content") and inv.content:
                for block in inv.content:
                    if block.get("type") == "text":
                        text_content = block.get("text", "")
                        messages.append({"role": "assistant", "content": text_content})
                    elif block.get("type") == "tool_use":
                        messages.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": block.get("id", ""),
                                        "type": "function",
                                        "function": {
                                            "name": block.get("name", ""),
                                            "arguments": json.dumps(
                                                block.get("input", {})
                                            ),
                                        },
                                    }
                                ],
                            }
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
        self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0),
        )

    async def stream(
        self,
        model: Model,
        invocations: list[Any],
        config: ChannelConfig,
    ) -> AsyncIterator[RealmResponse]:
        messages = _invocations_to_messages(invocations)

        payload = {
            "model": model.id,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
        }

        if config.mana_limit is not None:
            payload["max_tokens"] = min(config.max_tokens, config.mana_limit)

        response = await self._client.post(
            "/chat/completions",
            json=payload,
            timeout=config.timeout_ms / 1000,
        )

        if response.status_code != 200:
            content_type = response.headers.get("content-type", "")
            is_json = content_type.startswith("application/json")
            error_data = response.json() if is_json else {}
            msg = error_data.get("error", {}).get(
                "message", f"HTTP {response.status_code}"
            )
            yield RealmResponse(model=model, error_message=msg)
            return

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

            content = delta.get("content")
            tool_calls = delta.get("tool_calls")

            invocation = None
            if content or tool_calls:
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.get("id", ""),
                                "name": func.get("name", ""),
                                "input": json.loads(func.get("arguments", "{}")),
                            }
                        )
                from mvgeos_agent.types import MvgeResponse

                invocation = MvgeResponse(
                    role="assistant",
                    content=blocks,
                    realm="openrouter",
                    model=model.id,
                )

            usage = chunk.get("usage", {})
            mana_used = usage.get("total_tokens", 0)

            yield RealmResponse(
                model=model,
                invocation=invocation,
                mana_used=mana_used,
                stop_reason=finish_reason or "stop",
            )

    async def close(self) -> None:
        await self._client.aclose()
