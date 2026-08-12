from __future__ import annotations

import json
from pathlib import Path

from mvgeos_provider.types import Model

_MODELS_PATH = Path(__file__).parent / "models.json"


def _load_models_json() -> list[tuple[str, str, int, list[str], bool]]:
    try:
        data = json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
        free_entries = data.get("free", [])
        paid_entries = data.get("paid", [])
        result: list[tuple[str, str, int, list[str], bool]] = []
        for entry in free_entries:
            mid = entry[0]
            name = entry[1]
            ctx = entry[2]
            params = entry[3] if len(entry) > 3 else []
            result.append((mid, name, ctx, params, True))
        for entry in paid_entries:
            mid = entry[0]
            name = entry[1]
            ctx = entry[2]
            params = entry[3] if len(entry) > 3 else []
            result.append((mid, name, ctx, params, False))
        return result
    except json.JSONDecodeError, OSError:
        return []


MODELS: dict[str, Model] = {}

for mid, name, ctx, params, is_free in _load_models_json():
    MODELS[mid] = Model(
        id=mid,
        name=name,
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        max_completion_mana=0,
        context_window=ctx,
        max_tokens=4096,
        supported_parameters=params,
        is_free=is_free,
    )


def list_models() -> list[Model]:
    return list(MODELS.values())


def get_model(model_id: str) -> Model | None:
    return MODELS.get(model_id)
