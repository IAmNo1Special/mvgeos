from mvgeos_provider.base import Realm
from mvgeos_provider.types import Model


def test_realm_protocol_has_stream_method() -> None:
    assert hasattr(Realm, "stream")


def test_model_has_required_fields() -> None:
    model = Model(
        id="openrouter/test-model",
        name="Test Model",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        max_completion_mana=1000,
        context_window=128000,
        max_tokens=4096,
    )
    assert model.id == "openrouter/test-model"
    assert model.realm == "openrouter"
    assert model.max_completion_mana == 1000
    assert model.supported_parameters == []


def test_model_supported_parameters() -> None:
    model = Model(
        id="openrouter/openai/o1",
        name="Test Model",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        supported_parameters=["reasoning", "temperature"],
    )
    assert "reasoning" in model.supported_parameters
    assert "temperature" in model.supported_parameters
