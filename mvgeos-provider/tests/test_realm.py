import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx

from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse


class AsyncIterator:
    def __init__(self, items):
        self._items = items
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


async def collect_responses(iterator):
    return [item async for item in iterator]


def test_openrouter_realm_has_stream_method() -> None:
    realm = OpenRouterRealm(api_key="test-key")
    assert hasattr(realm, "stream")


def test_model_has_realm_field() -> None:
    model = Model(
        id="openrouter/test-model",
        name="Test Model",
        realm="openrouter",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
    )
    assert model.realm == "openrouter"


def test_openrouter_realm_stream_builds_correct_messages() -> None:
    from mvgeos_agent.types import MvgeResponse, SummonerRequest

    realm = OpenRouterRealm(api_key="test-key")
    model = Model(
        id="openrouter/test-model",
        name="Test Model",
        realm="openrouter",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
    )
    config = ChannelConfig(model=model)

    invocations: list[SummonerRequest | MvgeResponse] = [
        SummonerRequest(role="user", content="Hello"),
    ]

    mock_response = MagicMock()
    mock_response.aiter_lines.return_value = AsyncIterator([
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        (b'data: {"choices":[{"delta":{"content":" world"},"finish_reason":"stop"}]}\n\n'),
        b'data: [DONE]\n\n',
    ])
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}
    mock_response.text = ""
    mock_response.status_code = 200

    realm._client.post = AsyncMock(return_value=mock_response)

    responses = asyncio.run(collect_responses(realm.stream(model, invocations, config)))

    assert len(responses) >= 1
    assert responses[0].stop_reason == "stop"


def test_openrouter_realm_stream_handles_tool_calls() -> None:
    from mvgeos_agent.types import MvgeResponse

    realm = OpenRouterRealm(api_key="test-key")
    model = Model(
        id="openrouter/test-model",
        name="Test Model",
        realm="openrouter",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
    )
    config = ChannelConfig(model=model)

    invocations: list[MvgeResponse] = [
        MvgeResponse(
            role="assistant",
            content=[
                {
                    "type": "tool_use",
                    "id": "call_123",
                    "name": "bash",
                    "input": {"command": "echo hello"},
                }
            ],
        )
    ]

    mock_response = MagicMock()
    mock_response.aiter_lines.return_value = AsyncIterator([
        (
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_123",'
            b'"type":"function","function":{"name":"bash","arguments":"{\\"command\\":\\"echo hello\\"}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n',
        b'data: [DONE]\n\n',
    ])
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}
    mock_response.text = ""
    mock_response.status_code = 200

    realm._client.post = AsyncMock(return_value=mock_response)

    responses = asyncio.run(collect_responses(realm.stream(model, invocations, config)))

    assert len(responses) >= 1


def test_openrouter_realm_stream_error_handling() -> None:
    from mvgeos_agent.types import SummonerRequest

    realm = OpenRouterRealm(api_key="test-key")
    model = Model(
        id="openrouter/test-model",
        name="Test Model",
        realm="openrouter",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
    )
    config = ChannelConfig(model=model)

    invocations = [SummonerRequest(role="user", content="Hello")]

    mock_response = MagicMock()
    mock_response.aiter_lines.return_value = AsyncIterator([
        b'data: {"error":{"message":"Rate limit exceeded"}}\n\n',
    ])
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        "429", request=MagicMock(), response=MagicMock(status_code=429)
    ))
    mock_response.headers = {}
    mock_response.text = ""
    mock_response.status_code = 429

    realm._client.post = AsyncMock(return_value=mock_response)

    responses = asyncio.run(collect_responses(realm.stream(model, invocations, config)))

    assert len(responses) >= 1
    assert responses[0].error_message is not None


def test_openrouter_realm_close() -> None:
    realm = OpenRouterRealm(api_key="test-key")
    asyncio.run(realm.close())
    # Should not raise


def test_realm_response_has_mana_used() -> None:
    model = Model(
        id="test",
        name="Test",
        realm="test",
        provider="test",
        base_url="http://test",
        api_key="test",
    )
    response = RealmResponse(model=model, mana_used=100)
    assert response.mana_used == 100
