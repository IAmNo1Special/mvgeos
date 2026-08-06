from __future__ import annotations

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
    from mvgeos_provider.openrouter import OpenRouterRealm

    assert isinstance(realm, OpenRouterRealm)
