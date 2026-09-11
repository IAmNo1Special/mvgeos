from __future__ import annotations

import asyncio
from typing import Any

import httpx
from mvgeos_core.channel import Model

from mvgeos_provider.base import (
    NoRealmRegisteredError,
    Realm,
    RealmFactory,
)
from mvgeos_provider.model_registry import ModelRegistry
from mvgeos_provider.openrouter import OpenRouterRealm


class RealmRegistry:
    def __init__(
        self,
        shared_client: httpx.AsyncClient | None = None,
        model_registry: ModelRegistry | None = None,
        cache_ttl_seconds: int = 86400,
    ) -> None:
        self._shared_client = shared_client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._model_registry = model_registry or ModelRegistry(
            cache_ttl_seconds=cache_ttl_seconds
        )
        self._model_registry.load_cache()
        self._extension_providers: dict[str, dict[str, Any]] = {}
        self._realm_factories: dict[str, RealmFactory] = {}
        self._default_realm_factory: RealmFactory = (
            lambda api_key="", base_url="", **kwargs: OpenRouterRealm(
                api_key=api_key,
                base_url=base_url or "https://openrouter.ai/api/v1",
                client=self.get_shared_client(),
            )
        )
        self._realm_factories["openrouter"] = self._default_realm_factory

    @property
    def cache_ttl_seconds(self) -> int:
        return self._model_registry.cache_ttl_seconds

    @property
    def model_registry(self) -> ModelRegistry:
        return self._model_registry

    async def refresh_models(self, force_refresh: bool = False) -> int:
        """Refresh model catalog from provider APIs or cache.

        Args:
            force_refresh: If True, bypass disk cache and fetch live models.

        Returns:
            Number of models loaded from the API, or 0 if cache was used.
        """
        return await self._model_registry.refresh(force_refresh=force_refresh)

    def get_model_options(self) -> dict[str, str]:
        """Return model display options with free models first, sorted by id."""
        return self._model_registry.get_model_options()

    def get_flat_model_ids(self) -> list[str]:
        """Return all model IDs, filtering out internal ~ prefixes."""
        return self._model_registry.get_flat_model_ids()

    def get_shared_client(self) -> httpx.AsyncClient:
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._shared_client

    async def prewarm_client(self) -> httpx.AsyncClient:
        """Pre-warm the shared HTTP client in a thread to avoid event-loop blocking."""
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = await asyncio.to_thread(
                httpx.AsyncClient,
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._shared_client

    async def close(self) -> None:
        if self._shared_client is not None and not self._shared_client.is_closed:
            await self._shared_client.aclose()
            self._shared_client = None

    def register_provider(self, name: str, config: dict[str, Any]) -> None:
        if name not in self._extension_providers:
            self._extension_providers[name] = {}
        self._extension_providers[name].update(config)

    def get_provider_config(self, name: str) -> dict[str, Any] | None:
        return self._extension_providers.get(name)

    def get_registered_providers(self) -> list[str]:
        providers = list(self._extension_providers.keys())
        for rf in self._realm_factories:
            if rf not in providers and rf != "openrouter":
                providers.append(rf)
        return providers

    def register_realm_factory(self, prefix: str, factory: RealmFactory) -> None:
        """Register a pluggable RealmFactory for a provider prefix."""
        if not prefix or not isinstance(prefix, str) or not prefix.strip():
            raise ValueError("Prefix must be a non-empty string")
        if not callable(factory):
            raise TypeError(f"Realm factory for '{prefix}' must be callable")
        self._realm_factories[prefix.strip()] = factory

    def unregister_realm_factory(self, prefix: str) -> None:
        """Unregister a RealmFactory for a provider prefix."""
        self._realm_factories.pop(prefix, None)

    def clear_realm_factories(self) -> None:
        """Clear all registered realm factories."""
        self._realm_factories.clear()

    def get_realm_factory(self, prefix: str) -> RealmFactory | None:
        """Get the registered RealmFactory for a prefix, or None."""
        return self._realm_factories.get(prefix)

    def has_realm_factory(self, prefix: str) -> bool:
        """Check whether a RealmFactory is registered for a prefix."""
        return prefix in self._realm_factories

    def get_registered_realm_factories(self) -> list[str]:
        """Return a list of all registered realm factory prefixes."""
        return list(self._realm_factories.keys())

    def has_provider(self, name: str) -> bool:
        return name in self._extension_providers or name in self._realm_factories

    def _candidate_keys(
        self, model: Model, provider_name: str | None = None
    ) -> list[str]:
        candidates: list[str] = []
        if provider_name:
            candidates.append(provider_name)
        if model.realm and model.realm not in candidates:
            candidates.append(model.realm)
        if model.provider and model.provider not in candidates:
            candidates.append(model.provider)
        for part in model.id.split("/"):
            if part and part not in candidates:
                candidates.append(part)
        return candidates

    def _get_extension_config(
        self, model: Model, provider_name: str | None = None
    ) -> dict[str, Any] | None:
        for candidate in self._candidate_keys(model, provider_name):
            if candidate in self._extension_providers:
                return self._extension_providers[candidate]
        return None

    def _find_realm_factory(
        self, model: Model, provider_name: str | None = None
    ) -> RealmFactory | None:
        for candidate in self._candidate_keys(model, provider_name):
            if candidate != "openrouter" and candidate in self._realm_factories:
                return self._realm_factories[candidate]
        return None

    def create_realm(
        self,
        model: Model,
        api_key: str,
        provider_name: str | None = None,
    ) -> Realm:
        ext_config = self._get_extension_config(model, provider_name)
        base_url = (ext_config.get("baseUrl") if ext_config else None) or model.base_url
        key = (
            (ext_config.get("apiKey") if ext_config else None)
            or model.api_key
            or api_key
        )

        factory = self._find_realm_factory(model, provider_name)
        if factory is not None:
            return factory(api_key=key, base_url=base_url)

        if "openrouter" in self._realm_factories:
            return self._realm_factories["openrouter"](api_key=key, base_url=base_url)

        raise NoRealmRegisteredError(
            f"No Realm factory registered for model '{model.id}'. "
            "Run 'mvgeos rune install openrouter-realm' to install it from "
            "the central marketplace."
        )

    def compose_model(
        self,
        model_id: str,
        api_key: str,
        provider_name: str | None = None,
    ) -> Model | None:
        model_info = self._model_registry.get(model_id)
        if model_info is not None:
            model = Model(
                id=model_info.id,
                name=model_info.name,
                realm=model_info.realm,
                base_url=model_info.base_url,
                api_key=api_key,
                max_completion_mana=model_info.max_completion_mana,
                context_window=model_info.context_window,
                max_tokens=model_info.max_tokens,
                headers=dict(model_info.headers or {}),
                supported_parameters=list(model_info.supported_parameters),
                is_free=model_info.is_free,
            )
        else:
            target_provider = provider_name
            if not target_provider and "/" in model_id:
                target_provider = model_id.split("/")[0]

            if target_provider and self.has_provider(target_provider):
                model = Model(
                    id=model_id,
                    name=model_id,
                    realm=target_provider,
                    base_url="",
                    api_key=api_key,
                )
            else:
                return None

        ext_config = self._get_extension_config(model, provider_name)
        if ext_config is not None:
            if "baseUrl" in ext_config:
                model.base_url = str(ext_config["baseUrl"])
            if "apiKey" in ext_config:
                model.api_key = str(ext_config["apiKey"])
            ext_headers = ext_config.get("headers")
            if isinstance(ext_headers, dict):
                model.headers.update(ext_headers)

        return model

    def resolve(
        self,
        model_id: str,
        api_key: str,
        provider_name: str | None = None,
    ) -> tuple[Model, Realm]:
        """Look up model metadata across static baseline and cached catalog,
        and construct the paired (Model, Realm) in one call.

        Raises:
            ValueError: If the model cannot be resolved from baseline, cache,
                or registered providers.
        """
        model = self.compose_model(model_id, api_key, provider_name)
        if model is None:
            raise ValueError(f"Unknown model: {model_id}")
        realm = self.create_realm(model, api_key, provider_name)
        return model, realm


_DEFAULT_REGISTRY: RealmRegistry | None = None


def get_default_realm_registry() -> RealmRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = RealmRegistry()
    return _DEFAULT_REGISTRY


def get_model_options() -> dict[str, str]:
    """Return model display options with free models first, sorted by id."""
    return get_default_realm_registry().get_model_options()


def get_flat_model_ids() -> list[str]:
    """Return all valid model IDs (ignoring internal ~ prefixes)."""
    return get_default_realm_registry().get_flat_model_ids()


async def refresh_models(force_refresh: bool = False) -> int:
    """Refresh model catalog using the default realm registry."""
    return await get_default_realm_registry().refresh_models(
        force_refresh=force_refresh
    )
