from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mvgeos_provider.base import Realm
from mvgeos_provider.models import get_model
from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.types import Model


class RealmRegistry:
    def __init__(self) -> None:
        self._extension_providers: dict[str, dict[str, Any]] = {}
        self._builtin_providers: dict[str, Callable[..., Realm]] = {
            "openrouter": lambda api_key="", base_url="": OpenRouterRealm(
                api_key=api_key, base_url=base_url
            ),
        }

    def register_provider(self, name: str, config: dict[str, Any]) -> None:
        if name not in self._extension_providers:
            self._extension_providers[name] = {}
        self._extension_providers[name].update(config)

    def get_provider_config(self, name: str) -> dict[str, Any] | None:
        return self._extension_providers.get(name)

    def get_registered_providers(self) -> list[str]:
        return list(self._extension_providers.keys())

    def has_provider(self, name: str) -> bool:
        return name in self._extension_providers or name in self._builtin_providers

    def create_realm(
        self,
        model: Model,
        api_key: str,
        provider_name: str | None = None,
    ) -> Realm:
        pname = provider_name or model.provider
        ext_config = self._extension_providers.get(pname)
        if ext_config is not None:
            base_url = ext_config.get("baseUrl") or model.base_url
            key = ext_config.get("apiKey") or api_key
            realm_factory = self._builtin_providers.get(pname)
            if realm_factory is not None:
                return realm_factory(api_key=key, base_url=base_url)
            from mvgeos_provider.base import Realm as BaseRealm

            class _DynamicRealm(BaseRealm):
                def __init__(self, config: dict[str, Any]) -> None:
                    self._config = config
                    self._http_client: Any | None = None

                async def stream(
                    self,
                    model_obj: Model,
                    invocations: list[Any],
                    config: Any,
                ) -> Any:
                    from mvgeos_provider.openrouter import OpenRouterRealm

                    bu = self._config.get("baseUrl", "")
                    fallback = OpenRouterRealm(
                        api_key=self._config.get("apiKey", ""),
                        base_url=bu,
                    )
                    async for resp in fallback.stream(model_obj, invocations, config):
                        yield resp

                async def close(self) -> None:
                    if self._http_client is not None:
                        await self._http_client.aclose()

            return _DynamicRealm(ext_config)

        realm_factory = self._builtin_providers.get(
            pname,
            lambda api_key="", base_url="": OpenRouterRealm(
                api_key=api_key, base_url=base_url
            ),
        )
        return cast(Realm, realm_factory(api_key=api_key, base_url=model.base_url))

    def compose_model(
        self,
        model_id: str,
        api_key: str,
        provider_name: str | None = None,
    ) -> Model | None:
        model_info = get_model(model_id)
        if model_info is None:
            return None

        from mvgeos_provider.types import Model

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
        )

        pname = provider_name or model.provider
        ext_config = self._extension_providers.get(pname)
        if ext_config is not None:
            if "baseUrl" in ext_config:
                model.base_url = str(ext_config["baseUrl"])
            if "apiKey" in ext_config:
                model.api_key = str(ext_config["apiKey"])
            ext_headers = ext_config.get("headers")
            if isinstance(ext_headers, dict):
                model.headers.update(ext_headers)

        return model
