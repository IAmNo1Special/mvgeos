from unittest.mock import AsyncMock

import httpx
import pytest

from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import Model


@pytest.mark.asyncio
async def test_realm_registry_shared_client() -> None:
    """Verify RealmRegistry shares an httpx.AsyncClient instance across realms."""
    registry = RealmRegistry()
    client1 = registry.get_shared_client()
    client2 = registry.get_shared_client()

    assert client1 is client2
    assert not client1.is_closed

    await registry.close()
    assert client1.is_closed


@pytest.mark.asyncio
async def test_openrouter_realm_shared_client_lifecycle() -> None:
    """Verify OpenRouterRealm uses shared client and does not close unowned client."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False

    realm = OpenRouterRealm(
        api_key="test_key",
        base_url="https://openrouter.ai/api/v1",
        client=mock_client,
    )

    await realm.close()
    # Unowned client should NOT have aclose() called by realm.close()
    mock_client.aclose.assert_not_called()


@pytest.mark.asyncio
async def test_realm_registry_create_realm_reuses_client() -> None:
    """Verify create_realm passes shared client to OpenRouterRealm."""
    registry = RealmRegistry()
    model = Model(
        id="nvidia/nemotron-3-ultra-550b-a55b:free",
        name="Nemotron",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test_key",
    )

    realm = registry.create_realm(model, api_key="test_key")
    assert isinstance(realm, OpenRouterRealm)
    assert realm._client is registry.get_shared_client()

    await registry.close()
