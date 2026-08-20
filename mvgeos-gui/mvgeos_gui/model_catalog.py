"""Model catalog for the GUI: loads, categorizes, and provides model options."""

from __future__ import annotations

from mvgeos_provider.model_registry import ModelRegistry

_PROVIDER_LABELS = {
    "nvidia": "NVIDIA",
    "google": "Google",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "x-ai": "xAI",
    "qwen": "Qwen",
    "meta": "Meta",
    "moonshotai": "MoonshotAI",
    "poolside": "Poolside",
    "cohere": "Cohere",
    "inclusionai": "inclusionAI",
    "bytedance-seed": "ByteDance Seed",
    "sakana": "Sakana",
    "upstage": "Upstage",
    "thinkingmachines": "Thinking Machines",
    "openrouter": "OpenRouter",
    "aion-labs": "AionLabs",
    "kwaipilot": "Kwaipilot",
    "minimax": "MiniMax",
    "stepfun": "StepFun",
    "nex-agi": "Nex AGI",
    "z-ai": "Z.ai",
    "tencent": "Tencent",
    "perceptron": "Perceptron",
    "liquid": "LiquidAI",
    "meituan": "Meituan",
}


def _provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider, provider.title())


def get_model_options() -> dict[str, str]:
    registry = ModelRegistry()
    models = registry.list_all()

    free: dict[str, str] = {}
    paid: dict[str, str] = {}

    for model in models:
        if not model.id or model.id.startswith("~"):
            continue
        display = model.name or model.id
        if model.free:
            free[model.id] = display
        else:
            paid[model.id] = display

    result: dict[str, str] = {}
    for mid in sorted(free.keys()):
        result[mid] = free[mid]
    for mid in sorted(paid.keys()):
        result[mid] = paid[mid]

    return result


def get_flat_model_ids() -> list[str]:
    registry = ModelRegistry()
    return [m.id for m in registry.list_all() if m.id and not m.id.startswith("~")]


FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemini-2.5-pro",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
]
