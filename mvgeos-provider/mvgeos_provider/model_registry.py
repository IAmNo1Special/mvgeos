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
        self._load_baseline()

    @property
    def models(self) -> dict[str, Model]:
        return dict(self._models)

    def get(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def list_all(self) -> list[Model]:
        return list(self._models.values())

    def _load_baseline(self) -> None:
        for mid, name, ctx, params in _load_models_json():
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
            if mid not in self._models:
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
                )
        logger.info("Loaded %d models from cache", len(data.get("models", [])))
        return True

    async def refresh(self) -> int:
        new_count = 0
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(OPENROUTER_MODELS_URL, timeout=30)
                if response.status_code != 200:
                    logger.warning(
                        "OpenRouter models API returned %d", response.status_code
                    )
                    return 0
                api_data: list[dict[str, Any]] = response.json()
        except Exception:
            logger.exception("Failed to fetch OpenRouter models")
            return 0

        for entry in api_data:
            mid = entry.get("id", "")
            if not mid or mid in self._models:
                continue
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
            )
            new_count += 1

        self._save_cache(api_data)
        logger.info("Refreshed models: %d new from API", new_count)
        return new_count

    def _save_cache(self, api_data: list[dict[str, Any]]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache = {
                "_cached_at": time.time(),
                "models": [
                    {
                        "id": e.get("id", ""),
                        "name": e.get("name", ""),
                        "context_length": e.get("context_length", 4096),
                        "supported_parameters": e.get("supported_parameters", []),
                    }
                    for e in api_data
                ],
            }
            self._cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Failed to save models cache")
