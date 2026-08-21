from __future__ import annotations

from mvgeos_provider.base import Realm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import Model


class ModelComposer:
    """Compose a Model and its Realm from a model ID and credentials.

    Thin facade over RealmRegistry: resolves the model descriptor and
    constructs the matching realm in one step, raising ValueError for
    model IDs that cannot be resolved.
    """

    def __init__(self, registry: RealmRegistry) -> None:
        self._registry = registry

    def compose(
        self,
        model_id: str,
        api_key: str,
        provider_name: str | None = None,
    ) -> tuple[Model, Realm]:
        model = self._registry.compose_model(model_id, api_key, provider_name)
        if model is None:
            raise ValueError(f"Unknown model: {model_id}")
        realm = self._registry.create_realm(model, api_key, provider_name)
        return model, realm
