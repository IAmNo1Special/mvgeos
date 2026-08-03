from __future__ import annotations

import json
from pathlib import Path

from mvgeos_provider.types import Model

_MODELS_PATH = Path(__file__).parent / "models.json"


def _provider_from_id(model_id: str) -> str:
    return model_id.split("/")[1] if "/" in model_id else model_id


def _load_models_json() -> list[tuple[str, str, int, list[str]]]:
    try:
        data = json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
        free = data.get("free", [])
        paid = data.get("paid", [])
        result: list[tuple[str, str, int, list[str]]] = []
        for entry in free + paid:
            mid = entry[0]
            name = entry[1]
            ctx = entry[2]
            params = entry[3] if len(entry) > 3 else []
            result.append((mid, name, ctx, params))
        return result
    except json.JSONDecodeError, OSError:
        return []


MODELS: dict[str, Model] = {}

for mid, name, ctx, params in _load_models_json():
    MODELS[mid] = Model(
        id=mid,
        name=name,
        realm="openrouter",
        provider=_provider_from_id(mid),
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        mana_limit=0,
        context_window=ctx,
        max_tokens=4096,
        supported_parameters=params,
    )


def list_models() -> list[Model]:
    return list(MODELS.values())


def get_model(model_id: str) -> Model | None:
    return MODELS.get(model_id)
