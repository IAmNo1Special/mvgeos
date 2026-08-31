from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mvgeos_provider.base import Realm
from mvgeos_provider.model_registry import ModelRegistry
from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import Model


def test_register_provider() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "custom", {"apiKey": "sekret", "baseUrl": "https://custom.ai"}
    )
    config = reg.get_provider_config("custom")
    assert config is not None
    assert config["apiKey"] == "sekret"


def test_register_provider_overwrites_merges() -> None:
    reg = RealmRegistry()
    reg.register_provider("custom", {"apiKey": "sekret"})
    reg.register_provider("custom", {"baseUrl": "https://custom.ai"})
    config = reg.get_provider_config("custom")
    assert config is not None
    assert config["apiKey"] == "sekret"
    assert config["baseUrl"] == "https://custom.ai"


def test_get_provider_config_nonexistent() -> None:
    reg = RealmRegistry()
    assert reg.get_provider_config("nonexistent") is None


def test_get_registered_providers() -> None:
    reg = RealmRegistry()
    assert reg.get_registered_providers() == []
    reg.register_provider("a", {})
    reg.register_provider("b", {})
    providers = reg.get_registered_providers()
    assert "a" in providers
    assert "b" in providers


def test_has_provider_builtin() -> None:
    reg = RealmRegistry()
    assert reg.has_provider("openrouter")


def test_has_provider_extension() -> None:
    reg = RealmRegistry()
    reg.register_provider("custom", {})
    assert reg.has_provider("custom")


def test_has_provider_nonexistent() -> None:
    reg = RealmRegistry()
    assert not reg.has_provider("nonexistent")


def test_compose_model_no_extension() -> None:
    reg = RealmRegistry()
    model = reg.compose_model("openai/gpt-oss-20b:free", api_key="test-key")
    assert model is not None
    assert model.api_key == "test-key"


def test_compose_model_unknown() -> None:
    reg = RealmRegistry()
    model = reg.compose_model("nonexistent/model", api_key="test-key")
    assert model is None


def test_compose_model_with_extension_override() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "openai", {"baseUrl": "https://custom.openai.com", "apiKey": "ext-key"}
    )
    model = reg.compose_model("openrouter/openai/gpt-4", api_key="cli-key")
    if model is not None and model.provider == "openai":
        assert model.api_key == "ext-key"
        assert model.base_url == "https://custom.openai.com"


def test_create_realm_default_openrouter() -> None:
    reg = RealmRegistry()
    model = Model(
        id="test-model",
        name="Test",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
    )
    realm = reg.create_realm(model, api_key="test-key")
    assert isinstance(realm, OpenRouterRealm)


def test_compose_model_prioritizes_realm_over_provider() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "openrouter",
        {"apiKey": "openrouter-key", "baseUrl": "https://openrouter.ai/api/v1"},
    )
    model = reg.compose_model("nvidia/nemotron-3.5-lightning:free", api_key="cli-key")
    assert model is not None
    assert model.api_key == "openrouter-key"
    assert model.base_url == "https://openrouter.ai/api/v1"


def test_create_realm_prioritizes_realm_over_provider() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "openrouter",
        {"apiKey": "openrouter-key", "baseUrl": "https://openrouter.ai/api/v1"},
    )
    model = Model(
        id="nvidia/nemotron-3.5-lightning:free",
        name="Nemotron",
        realm="openrouter",
        base_url="https://original.url",
        api_key="cli-key",
    )
    realm = reg.create_realm(model, api_key="cli-key")
    assert isinstance(realm, OpenRouterRealm)
    assert realm._api_key == "openrouter-key"
    assert realm._base_url == "https://openrouter.ai/api/v1"


def test_compose_model_fallback_for_unlisted_model() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "ollama", {"baseUrl": "http://localhost:11434", "apiKey": "ollama-key"}
    )
    model = reg.compose_model("ollama/llama3", api_key="cli-key")
    assert model is not None
    assert model.id == "ollama/llama3"
    assert model.realm == "ollama"
    assert model.api_key == "ollama-key"
    assert model.base_url == "http://localhost:11434"


def test_compose_model_fallback_with_explicit_provider_name() -> None:
    reg = RealmRegistry()
    reg.register_provider("vllm", {"baseUrl": "http://localhost:8000"})
    model = reg.compose_model(
        "custom-model-id", api_key="cli-key", provider_name="vllm"
    )
    assert model is not None
    assert model.id == "custom-model-id"
    assert model.realm == "vllm"
    assert model.base_url == "http://localhost:8000"


def test_resolve_returns_model_and_realm() -> None:
    reg = RealmRegistry()
    model, realm = reg.resolve("openai/gpt-oss-20b:free", api_key="test-key")
    assert isinstance(model, Model)
    assert model.id == "openai/gpt-oss-20b:free"
    assert model.api_key == "test-key"
    assert isinstance(realm, OpenRouterRealm)


def test_resolve_unknown_model_raises() -> None:
    reg = RealmRegistry()
    with pytest.raises(ValueError, match="Unknown model: nonexistent/model"):
        reg.resolve("nonexistent/model", api_key="test-key")


def test_resolve_unlisted_model_with_registered_prefix() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "ollama", {"baseUrl": "http://localhost:11434", "apiKey": "ollama-key"}
    )
    model, realm = reg.resolve("ollama/llama3", api_key="cli-key")
    assert model.id == "ollama/llama3"
    assert model.realm == "ollama"
    assert model.api_key == "ollama-key"
    assert model.base_url == "http://localhost:11434"
    assert isinstance(realm, Realm)


def test_resolve_with_explicit_provider_name() -> None:
    reg = RealmRegistry()
    reg.register_provider("vllm", {"baseUrl": "http://localhost:8000"})
    model, realm = reg.resolve(
        "custom-model-id", api_key="cli-key", provider_name="vllm"
    )
    assert model.id == "custom-model-id"
    assert model.realm == "vllm"
    assert model.base_url == "http://localhost:8000"
    assert isinstance(realm, Realm)


def test_resolve_extension_overrides_apply_to_model_and_realm() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "openai",
        {"baseUrl": "https://custom.openai.com", "apiKey": "ext-key"},
    )
    model, realm = reg.resolve("openai/gpt-4", api_key="cli-key")
    assert model.api_key == "ext-key"
    assert model.base_url == "https://custom.openai.com"
    assert isinstance(realm, OpenRouterRealm)


def test_resolve_cached_model(tmp_path: Path) -> None:
    cache_file = tmp_path / "models.json"
    cache_payload = {
        "_cached_at": 1000.0,
        "models": [
            {
                "id": "community/cached-model-99b",
                "name": "Cached 99B Model",
                "context_length": 32768,
                "supported_parameters": ["tools", "temperature"],
                "is_free": False,
            }
        ],
    }
    cache_file.write_text(json.dumps(cache_payload), encoding="utf-8")

    model_reg = ModelRegistry(cache_path=cache_file)
    with patch("time.time", return_value=1050.0):
        reg = RealmRegistry(model_registry=model_reg)
        model, realm = reg.resolve("community/cached-model-99b", api_key="test-key")

    assert model.id == "community/cached-model-99b"
    assert model.name == "Cached 99B Model"
    assert model.context_window == 32768
    assert model.supported_parameters == ["tools", "temperature"]
    assert model.api_key == "test-key"
    assert isinstance(realm, OpenRouterRealm)


def test_realm_registry_get_model_options_and_flat_ids() -> None:
    from mvgeos_provider.registry import get_flat_model_ids, get_model_options

    reg = RealmRegistry()
    options = reg.get_model_options()
    assert isinstance(options, dict)
    assert len(options) > 0

    flat_ids = reg.get_flat_model_ids()
    assert isinstance(flat_ids, list)
    assert len(flat_ids) > 0

    # Top-level helper functions
    top_options = get_model_options()
    top_flat_ids = get_flat_model_ids()
    assert top_options == options
    assert top_flat_ids == flat_ids
