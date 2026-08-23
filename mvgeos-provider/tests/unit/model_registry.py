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
