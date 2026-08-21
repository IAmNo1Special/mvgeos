from __future__ import annotations

import pytest

from mvgeos_provider.base import Realm
from mvgeos_provider.composer import ModelComposer
from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import Model


def test_compose_returns_model_and_realm() -> None:
    composer = ModelComposer(RealmRegistry())
    model, realm = composer.compose("openai/gpt-oss-20b:free", api_key="test-key")
    assert isinstance(model, Model)
    assert model.id == "openai/gpt-oss-20b:free"
    assert model.api_key == "test-key"
    assert isinstance(realm, OpenRouterRealm)


def test_compose_unknown_model_raises() -> None:
    composer = ModelComposer(RealmRegistry())
    with pytest.raises(ValueError, match="Unknown model"):
        composer.compose("nonexistent/model", api_key="test-key")


def test_compose_unlisted_model_with_registered_prefix() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "ollama", {"baseUrl": "http://localhost:11434", "apiKey": "ollama-key"}
    )
    composer = ModelComposer(reg)
    model, realm = composer.compose("ollama/llama3", api_key="cli-key")
    assert model.id == "ollama/llama3"
    assert model.realm == "ollama"
    assert model.api_key == "ollama-key"
    assert model.base_url == "http://localhost:11434"
    assert isinstance(realm, Realm)


def test_compose_with_explicit_provider_name() -> None:
    reg = RealmRegistry()
    reg.register_provider("vllm", {"baseUrl": "http://localhost:8000"})
    composer = ModelComposer(reg)
    model, realm = composer.compose(
        "custom-model-id", api_key="cli-key", provider_name="vllm"
    )
    assert model.id == "custom-model-id"
    assert model.realm == "vllm"
    assert model.base_url == "http://localhost:8000"
    assert isinstance(realm, Realm)


def test_compose_extension_overrides_apply_to_model_and_realm() -> None:
    reg = RealmRegistry()
    reg.register_provider(
        "openai",
        {"baseUrl": "https://custom.openai.com", "apiKey": "ext-key"},
    )
    composer = ModelComposer(reg)
    model, realm = composer.compose("openai/gpt-4", api_key="cli-key")
    assert model.api_key == "ext-key"
    assert model.base_url == "https://custom.openai.com"
    assert isinstance(realm, OpenRouterRealm)
