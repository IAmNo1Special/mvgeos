import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mvgeos_provider.model_registry import (
    CACHE_TTL_SECONDS,
    ModelRegistry,
    _is_free_entry,
)
from mvgeos_provider.types import Model


def test_is_free_entry_free_suffix() -> None:
    assert _is_free_entry({"id": "openai/gpt-4:free"}) is True
    assert _is_free_entry({"id": "openrouter/free"}) is True


def test_is_free_entry_pricing_zero() -> None:
    assert (
        _is_free_entry({"id": "x", "pricing": {"prompt": "0", "completion": "0"}})
        is True
    )
    assert (
        _is_free_entry({"id": "x", "pricing": {"prompt": "1", "completion": "0"}})
        is False
    )


def test_is_free_entry_no_pricing() -> None:
    assert _is_free_entry({"id": "x"}) is False
    assert _is_free_entry({"id": "x", "pricing": "bad"}) is False
    assert (
        _is_free_entry({"id": "x", "pricing": {"prompt": "bad", "completion": "bad"}})
        is False
    )


def test_load_cache_missing(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "cache.json")
    assert reg.load_cache() is False


def test_load_cache_valid(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {"_cached_at": time.time(), "models": [{"id": "a/b", "name": "A B"}]}
        ),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path)
    assert reg.load_cache() is True
    assert reg.get("a/b") is not None
    assert reg.needs_refresh() is False


def test_load_cache_expired(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps({"_cached_at": time.time() - CACHE_TTL_SECONDS - 10, "models": []}),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path)
    assert reg.load_cache() is False


def test_load_cache_corrupt(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("not json", encoding="utf-8")
    reg = ModelRegistry(cache_path=cache_path)
    assert reg.load_cache() is False


def test_needs_refresh_initial(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    assert reg.needs_refresh() is True


@pytest.mark.asyncio
async def test_auto_refresh_when_fresh(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    reg._refreshed = True
    assert await reg.auto_refresh() == 0


@pytest.mark.asyncio
async def test_refresh_success(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {
                "id": "a/b",
                "name": "A B",
                "context_length": 4096,
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {"id": "c/d", "name": "C D", "pricing": {"prompt": "1", "completion": "1"}},
            {"id": "", "name": "bad"},
        ]
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)
    with patch(
        "mvgeos_provider.model_registry.httpx.AsyncClient", return_value=mock_client
    ):
        count = await reg.refresh()
    assert count == 2
    assert reg.get("a/b").is_free is True
    assert reg.get("c/d").is_free is False


@pytest.mark.asyncio
async def test_refresh_handles_exception(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    with patch(
        "mvgeos_provider.model_registry.httpx.AsyncClient",
        side_effect=Exception("boom"),
    ):
        assert await reg.refresh() == 0


def test_save_cache_creates_file(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "sub" / "c.json")
    reg._save_cache([{"id": "x/y", "name": "X Y"}])
    assert (tmp_path / "sub" / "c.json").exists()


def test_get_model_options_sorting_and_filtering(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    reg._models.clear()
    reg._models["beta/paid"] = Model(
        id="beta/paid",
        name="Beta Paid",
        realm="openrouter",
        base_url="",
        api_key="",
        is_free=False,
    )
    reg._models["alpha/free"] = Model(
        id="alpha/free",
        name="Alpha Free",
        realm="openrouter",
        base_url="",
        api_key="",
        is_free=True,
    )
    reg._models["zeta/free"] = Model(
        id="zeta/free",
        name="Zeta Free",
        realm="openrouter",
        base_url="",
        api_key="",
        is_free=True,
    )
    reg._models["alpha/paid"] = Model(
        id="alpha/paid",
        name="Alpha Paid",
        realm="openrouter",
        base_url="",
        api_key="",
        is_free=False,
    )
    reg._models["~internal/hidden"] = Model(
        id="~internal/hidden",
        name="Hidden",
        realm="openrouter",
        base_url="",
        api_key="",
        is_free=True,
    )

    options = reg.get_model_options()
    keys = list(options.keys())

    # Free models come first, sorted by id
    assert keys[:2] == ["alpha/free", "zeta/free"]
    # Paid models come next, sorted by id
    assert keys[2:] == ["alpha/paid", "beta/paid"]
    # Internal ~ models are excluded
    assert "~internal/hidden" not in options


def test_get_flat_model_ids(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    reg._models.clear()
    reg._models["a/model"] = Model(
        id="a/model", name="A Model", realm="openrouter", base_url="", api_key=""
    )
    reg._models["b/model"] = Model(
        id="b/model", name="B Model", realm="openrouter", base_url="", api_key=""
    )
    reg._models["~hidden"] = Model(
        id="~hidden", name="Hidden", realm="openrouter", base_url="", api_key=""
    )

    ids = reg.get_flat_model_ids()
    assert "a/model" in ids
    assert "b/model" in ids
    assert "~hidden" not in ids


def test_init_cache_ttl_configurable(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json", cache_ttl_seconds=3600)
    assert reg.cache_ttl_seconds == 3600
    default_reg = ModelRegistry(cache_path=tmp_path / "c2.json")
    assert default_reg.cache_ttl_seconds == CACHE_TTL_SECONDS


def test_load_cache_custom_ttl_hit(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {"_cached_at": time.time() - 500, "models": [{"id": "a/b", "name": "A B"}]}
        ),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path, cache_ttl_seconds=1000)
    assert reg.load_cache() is True
    assert reg.get("a/b") is not None


def test_load_cache_custom_ttl_expired(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {"_cached_at": time.time() - 500, "models": [{"id": "a/b", "name": "A B"}]}
        ),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path, cache_ttl_seconds=300)
    assert reg.load_cache() is False


def test_load_cache_force_refresh_bypasses_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {"_cached_at": time.time(), "models": [{"id": "a/b", "name": "A B"}]}
        ),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path)
    assert reg.load_cache(force_refresh=True) is False


@pytest.mark.asyncio
async def test_refresh_with_valid_cache_returns_zero_without_network(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {"_cached_at": time.time(), "models": [{"id": "a/b", "name": "A B"}]}
        ),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path)
    assert reg.load_cache() is True

    with patch("mvgeos_provider.model_registry.httpx.AsyncClient") as mock_client_cls:
        count = await reg.refresh(force_refresh=False)
        assert count == 0
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_force_refresh_bypasses_valid_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {"_cached_at": time.time(), "models": [{"id": "a/b", "name": "A B"}]}
        ),
        encoding="utf-8",
    )
    reg = ModelRegistry(cache_path=cache_path)
    assert reg.load_cache() is True

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "new/model", "name": "New Model"},
        ]
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch(
        "mvgeos_provider.model_registry.httpx.AsyncClient", return_value=mock_client
    ):
        count = await reg.refresh(force_refresh=True)

    assert count == 1
    assert reg.get("new/model") is not None


@pytest.mark.asyncio
async def test_auto_refresh_force_refresh(tmp_path: Path) -> None:
    reg = ModelRegistry(cache_path=tmp_path / "c.json")
    reg._refreshed = True

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "live/model", "name": "Live Model"},
        ]
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch(
        "mvgeos_provider.model_registry.httpx.AsyncClient", return_value=mock_client
    ):
        count = await reg.auto_refresh(force_refresh=True)

    assert count == 1
    assert reg.get("live/model") is not None
