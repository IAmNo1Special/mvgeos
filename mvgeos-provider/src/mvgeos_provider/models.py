from __future__ import annotations

from mvgeos_provider.model_registry import _load_baseline_models
from mvgeos_provider.types import Model


def list_models() -> list[Model]:
    return list(_load_baseline_models().values())
