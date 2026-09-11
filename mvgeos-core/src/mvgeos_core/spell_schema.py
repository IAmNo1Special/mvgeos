from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, cast, get_type_hints

from pydantic import create_model


def generate_spell_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate a JSON schema from a spell function's signature and type hints."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    fields: dict[str, tuple[Any, Any]] = {}
    for param_name, param in sig.parameters.items():
        if param_name in ("spell_cast_id", "params", "signal", "on_update", "client"):
            continue
        annotation = type_hints.get(param_name, Any)
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param_name] = (annotation, default)

    if not fields:
        schema_model = create_model("EmptyParams")
    else:
        schema_model = create_model(
            f"{func.__name__}Params", **cast(dict[str, Any], fields)
        )

    schema = schema_model.model_json_schema()
    return schema
