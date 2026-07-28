from mvgeos_provider.types import Model

MODELS: dict[str, Model] = {
    "openrouter/anthropic/claude-3.5-sonnet": Model(
        id="openrouter/anthropic/claude-3.5-sonnet",
        name="Claude 3.5 Sonnet",
        realm="openrouter",
        provider="anthropic",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        mana_limit=0,
        context_window=200000,
        max_tokens=4096,
    ),
    "openrouter/openai/gpt-4o": Model(
        id="openrouter/openai/gpt-4o",
        name="GPT-4o",
        realm="openrouter",
        provider="openai",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        mana_limit=0,
        context_window=128000,
        max_tokens=4096,
    ),
}


def list_models() -> list[Model]:
    return list(MODELS.values())


def get_model(model_id: str) -> Model | None:
    return MODELS.get(model_id)
