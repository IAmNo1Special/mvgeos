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


def test_channel_config_system_prompt() -> None:
    from mvgeos_provider.types import ChannelConfig

    model = Model(
        id="openrouter/test-model",
        name="Test",
        realm="openrouter",
        base_url="",
        api_key="",
    )
    default_config = ChannelConfig(model=model)
    assert default_config.system_prompt == ""

    custom_config = ChannelConfig(model=model, system_prompt="You are a Mvge.")
    assert custom_config.system_prompt == "You are a Mvge."


def test_realm_response_has_diagnostic_fields() -> None:
    from mvgeos_provider.types import RealmResponse

    model = Model(
        id="openrouter/test-model",
        name="Test",
        realm="openrouter",
        base_url="",
        api_key="",
    )
    resp = RealmResponse(
        model=model,
        error_message="Rate limit exceeded",
        error_code="rate_limited",
        retry_after=15.0,
        limit_source="openrouter_free_tier_daily",
        remedy_hint="Add credits to unlock 1000 requests",
        reset_at=1788566400.0,
        quota_limit=50,
        quota_remaining=0,
    )
    assert resp.retry_after == 15.0
    assert resp.limit_source == "openrouter_free_tier_daily"
    assert resp.remedy_hint == "Add credits to unlock 1000 requests"
    assert resp.reset_at == 1788566400.0
    assert resp.quota_limit == 50
    assert resp.quota_remaining == 0
