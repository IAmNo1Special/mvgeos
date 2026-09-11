from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from mvgeos_core.channel import Model

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS = 86400

_MODELS_PATH = Path(__file__).parent / "models.json"


_DEFAULT_CONTEMPLATION_LEVELS: list[str] = [
    "none",
    "low",
    "medium",
    "high",
    "x-high",
]


def _create_openrouter_model(
    id: str,
    name: str,
    context_window: int = 4096,
    supported_parameters: list[str] | None = None,
    is_free: bool = False,
    supported_contemplation_levels: list[str] | None = None,
) -> Model:
    params = supported_parameters or []
    if supported_contemplation_levels is not None:
        levels = list(supported_contemplation_levels)
    elif any(
        p in params
        for p in ("reasoning", "thinking", "include_reasoning", "reasoning_effort")
    ) or any(m in id for m in ("openai/o1", "openai/o3")):
        levels = list(_DEFAULT_CONTEMPLATION_LEVELS)
    else:
        levels = []

    return Model(
        id=id,
        name=name,
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        max_completion_mana=0,
        context_window=context_window,
        max_tokens=4096,
        supported_parameters=params,
        supported_contemplation_levels=levels,
        is_free=is_free,
    )


def _load_models_json() -> list[tuple[str, str, int, list[str], bool]]:
    try:
        data = json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
        result: list[tuple[str, str, int, list[str], bool]] = []
        for is_free, key in ((True, "free"), (False, "paid")):
            for entry in data.get(key, []):
                mid = entry[0]
                name = entry[1]
                ctx = entry[2]
                params = entry[3] if len(entry) > 3 else []
                result.append((mid, name, ctx, params, is_free))
        return result
    except (json.JSONDecodeError, OSError):
        return []


def _load_baseline_models() -> dict[str, Model]:
    return {
        mid: _create_openrouter_model(
            id=mid,
            name=name,
            context_window=ctx,
            supported_parameters=params,
            is_free=is_free,
        )
        for mid, name, ctx, params, is_free in _load_models_json()
    }


def list_models() -> list[Model]:
    return list(_load_baseline_models().values())


def _default_cache_path() -> Path:
    return Path("~/.agents/models.json").expanduser()


class ModelRegistry:
    def __init__(
        self,
        cache_path: Path | None = None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._models: dict[str, Model] = {}
        self._cache_path = cache_path or _default_cache_path()
        self._cache_ttl_seconds = cache_ttl_seconds
        self._refreshed = False
        self._load_baseline()

    @property
    def cache_ttl_seconds(self) -> int:
        return self._cache_ttl_seconds

    @property
    def models(self) -> dict[str, Model]:
        return dict(self._models)

    def get(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def list_all(self) -> list[Model]:
        return list(self._models.values())

    def get_model_options(self) -> dict[str, str]:
        """Return model display options with free models first, sorted by id."""
        models = self.list_all()
        free: dict[str, str] = {}
        paid: dict[str, str] = {}

        for model in models:
            if not model.id or model.id.startswith("~"):
                continue
            display = model.name or model.id
            if model.free:
                free[model.id] = display
            else:
                paid[model.id] = display

        result: dict[str, str] = {}
        for mid in sorted(free.keys()):
            result[mid] = free[mid]
        for mid in sorted(paid.keys()):
            result[mid] = paid[mid]
        return result

    def get_flat_model_ids(self) -> list[str]:
        """Return all model IDs, filtering out internal ~ prefixes."""
        return [m.id for m in self.list_all() if m.id and not m.id.startswith("~")]

    def get_providers_for_realm(self, realm: str = "openrouter") -> list[str]:
        """Return sorted unique list of provider prefixes for models in the realm."""
        providers: set[str] = set()
        for m in self.list_all():
            if m.realm == realm and m.provider_prefix:
                providers.add(m.provider_prefix)
        return sorted(providers)

    def get_models_for_provider(
        self, provider: str, realm: str = "openrouter"
    ) -> list[Model]:
        """Return list of Model instances matching the given provider and realm."""
        return [
            m
            for m in self.list_all()
            if m.realm == realm and m.provider_prefix == provider
        ]

    def get_supported_contemplation_levels(self, model_id: str) -> list[str]:
        """Return supported contemplation levels for model ID, or empty list."""
        model = self.get(model_id)
        if model is None:
            return []
        return list(model.supported_contemplation_levels)

    def _load_baseline(self) -> None:
        self._models.update(_load_baseline_models())

    def load_cache(self, force_refresh: bool = False) -> bool:
        if force_refresh:
            return False
        if not self._cache_path.exists():
            return False
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        timestamp = data.get("_cached_at", 0)
        if time.time() - timestamp > self._cache_ttl_seconds:
            return False
        for entry in data.get("models", []):
            mid = entry["id"]
            self._models[mid] = _create_openrouter_model(
                id=mid,
                name=entry.get("name", mid),
                context_window=entry.get("context_length", 4096),
                supported_parameters=entry.get("supported_parameters", []),
                is_free=entry.get("is_free", False),
                supported_contemplation_levels=entry.get(
                    "supported_contemplation_levels"
                ),
            )
        self._refreshed = True
        logger.info("Loaded %d models from cache", len(data.get("models", [])))
        return True

    def needs_refresh(self) -> bool:
        """Return True if no valid cache has been loaded yet."""
        return not self._refreshed

    async def auto_refresh(self, force_refresh: bool = False) -> int:
        """Refresh only if cache is stale or missing (unless forced).

        Returns the number of models loaded from the API, or 0 if
        the cache was already fresh.
        """
        if not force_refresh and not self.needs_refresh():
            return 0
        return await self.refresh(force_refresh=force_refresh)

    async def refresh(
        self,
        force_refresh: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> int:
        if not force_refresh and (self._refreshed or self.load_cache()):
            return 0

        count = 0
        try:
            if client is not None:
                response = await client.get(OPENROUTER_MODELS_URL, timeout=30)
            else:
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(OPENROUTER_MODELS_URL, timeout=30)

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
            levels = (
                entry.get("supported_contemplation_levels")
                or entry.get("contemplation_levels")
                or entry.get("reasoning_levels")
            )
            self._models[mid] = _create_openrouter_model(
                id=mid,
                name=entry.get("name", mid),
                context_window=entry.get("context_length", 4096),
                supported_parameters=entry.get("supported_parameters", []),
                is_free=_is_free_entry(entry),
                supported_contemplation_levels=levels,
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
                        "supported_contemplation_levels": (
                            self._models[e["id"]].supported_contemplation_levels
                            if e.get("id") in self._models
                            else (e.get("supported_contemplation_levels") or [])
                        ),
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
    except (ValueError, TypeError):
        return False
