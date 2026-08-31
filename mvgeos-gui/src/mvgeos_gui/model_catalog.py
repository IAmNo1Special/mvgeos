"""Model catalog for the GUI: loads, categorizes, and provides model options."""

from __future__ import annotations

from mvgeos_provider.model_registry import ModelRegistry

_MODEL_REGISTRY: ModelRegistry | None = None


def _get_registry() -> ModelRegistry:
    global _MODEL_REGISTRY
    if _MODEL_REGISTRY is None:
        _MODEL_REGISTRY = ModelRegistry()
    return _MODEL_REGISTRY


def get_model_options() -> dict[str, str]:
    registry = _get_registry()
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
    return [
        m.id for m in _get_registry().list_all() if m.id and not m.id.startswith("~")
    ]
