from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from mvgeos_provider.models import _load_models_json
from mvgeos_provider.types import Model

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS = 86400


def _default_cache_path() -> Path:
    return Path("~/.agents/.mvgeos/openrouter_models.json").expanduser()


class ModelRegistry:
    def __init__(self, cache_path: Path | None = None) -> None:
        self._models: dict[str, Model] = {}
        self._cache_path = cache_path or _default_cache_path()
        self._refreshed = False
        self._load_baseline()

    @property
    def models(self) -> dict[str, Model]:
        return dict(self._models)

    def get(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def list_all(self) -> list[Model]:
        return list(self._models.values())

    def _load_baseline(self) -> None:
        for mid, name, ctx, params, is_free in _load_models_json():
            self._models[mid] = Model(
                id=mid,
                name=name,
                realm="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key="",
                max_completion_mana=0,
                context_window=ctx,
                max_tokens=4096,
                supported_parameters=params,
                is_free=is_free,
            )

    def load_cache(self) -> bool:
        if not self._cache_path.exists():
            return False
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            return False
        timestamp = data.get("_cached_at", 0)
        if time.time() - timestamp > CACHE_TTL_SECONDS:
            return False
        for entry in data.get("models", []):
            mid = entry["id"]
            self._models[mid] = Model(
                id=mid,
                name=entry.get("name", mid),
                realm="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key="",
                max_completion_mana=0,
                context_window=entry.get("context_length", 4096),
                max_tokens=4096,
                supported_parameters=entry.get("supported_parameters", []),
                is_free=entry.get("is_free", False),
            )
        self._refreshed = True
        logger.info("Loaded %d models from cache", len(data.get("models", [])))
        return True

    def needs_refresh(self) -> bool:
        """Return True if no valid cache has been loaded yet."""
        return not self._refreshed

    async def auto_refresh(self) -> int:
        """Refresh only if cache is stale or missing.

        Returns the number of models loaded from the API, or 0 if
        the cache was already fresh.
        """
        if not self.needs_refresh():
            return 0
        return await self.refresh()

    async def refresh(self) -> int:
        count = 0
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(OPENROUTER_MODELS_URL, timeout=30)
                if response.status_code != 200:
                    logger.warning(
                        "OpenRouter models API returned %d",
                        response.status_code,
                    )
                res_json = response.json()
                if isinstance(res_json, dict):
                    api_data: list[dict[str, Any]] = res_json.get("data", [])
                elif isinstance(res_json, list):
                    api_data = res_json
                else:
                    api_data = []
        except Exception:
            logger.exception("Failed to fetch OpenRouter models")
            return 0

        for entry in api_data:
            mid = entry.get("id", "")
            if not mid:
                continue
            pricing = entry.get("pricing", {})
            try:
                prompt_cost = float(pricing.get("prompt", "1"))
                completion_cost = float(pricing.get("completion", "1"))
            except ValueError, TypeError:
                prompt_cost = 1.0
                completion_cost = 1.0
            is_free = (
                (prompt_cost == 0 and completion_cost == 0)
                or mid.endswith(":free")
                or mid == "openrouter/free"
            )
            self._models[mid] = Model(
                id=mid,
                name=entry.get("name", mid),
                realm="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key="",
                max_completion_mana=0,
                context_window=entry.get("context_length", 4096),
                max_tokens=4096,
                supported_parameters=entry.get("supported_parameters", []),
                is_free=is_free,
            )
            count += 1

        self._save_cache(api_data)
        self._refreshed = True
        logger.info("Refreshed models: %d from API", count)
        return count

    def _save_cache(self, api_data: list[dict[str, Any]]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache: dict[str, Any] = {
                "_cached_at": time.time(),
                "models": [
                    {
                        "id": e.get("id", ""),
                        "name": e.get("name", ""),
                        "context_length": e.get("context_length", 4096),
                        "supported_parameters": e.get("supported_parameters", []),
                        "is_free": _is_free_entry(e),
                    }
                    for e in api_data
                ],
            }
            self._cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Failed to save models cache")


def _is_free_entry(entry: dict[str, Any]) -> bool:
    """Determine if an API model entry is free."""
    mid = entry.get("id", "")
    if mid.endswith(":free") or mid == "openrouter/free":
        return True
    pricing = entry.get("pricing")
    if not isinstance(pricing, dict):
        return False
    try:
        return (
            float(pricing.get("prompt", "1")) == 0
            and float(pricing.get("completion", "1")) == 0
        )
    except ValueError, TypeError:
        return False
