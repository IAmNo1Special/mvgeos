from __future__ import annotations

from mvgeos_core.channel import Model


def test_model_supported_contemplation_levels_default() -> None:
    model = Model(
        id="test/model",
        name="Test Model",
        realm="test",
        base_url="https://example.com",
        api_key="key",
    )
    assert model.supported_contemplation_levels == []
    assert model.supports_contemplation is False


def test_model_supports_contemplation_via_levels() -> None:
    model = Model(
        id="test/model",
        name="Test Model",
        realm="test",
        base_url="https://example.com",
        api_key="key",
        supported_contemplation_levels=["none", "low", "medium", "high", "x-high"],
    )
    assert model.supports_contemplation is True
    assert model.supported_contemplation_levels == [
        "none",
        "low",
        "medium",
        "high",
        "x-high",
    ]


def test_model_supports_contemplation_via_parameters() -> None:
    model_reasoning = Model(
        id="test/model-reasoning",
        name="Reasoning Model",
        realm="test",
        base_url="https://example.com",
        api_key="key",
        supported_parameters=["reasoning"],
    )
    assert model_reasoning.supports_contemplation is True

    model_thinking = Model(
        id="test/model-thinking",
        name="Thinking Model",
        realm="test",
        base_url="https://example.com",
        api_key="key",
        supported_parameters=["thinking"],
    )
    assert model_thinking.supports_contemplation is True


def test_model_provider_prefix() -> None:
    # With slash in id
    m1 = Model(
        id="anthropic/claude-3-5-sonnet",
        name="Claude",
        realm="openrouter",
        base_url="https://example.com",
        api_key="key",
    )
    assert m1.provider_prefix == "anthropic"

    # Without slash, with realm
    m2 = Model(
        id="gemini-2.5-flash",
        name="Gemini",
        realm="google",
        base_url="https://example.com",
        api_key="key",
    )
    assert m2.provider_prefix == "google"

    # Without slash, without realm
    m3 = Model(
        id="custom-direct-model",
        name="Custom",
        realm="",
        base_url="https://example.com",
        api_key="key",
    )
    assert m3.provider_prefix == "custom-direct-model"
