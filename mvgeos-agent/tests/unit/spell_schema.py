from typing import Any

import pytest
from pydantic import ValidationError

from mvgeos_agent.spell_schema import generate_spell_schema, validate_spell_args


def test_generate_empty_params() -> None:
    def no_params(spell_cast_id: str) -> str:
        return "ok"

    schema = generate_spell_schema(no_params)
    assert schema["properties"] == {}
    assert "required" not in schema or schema["required"] == []


def test_generate_with_all_param_types() -> None:
    def spell(
        spell_cast_id: str,
        name: str,
        count: int,
        ratio: float,
        flag: bool,
        items: list[str],
        meta: dict[str, Any],
        optional: str = "default",
    ) -> str:
        return "ok"

    schema = generate_spell_schema(spell)
    props = schema["properties"]
    assert props["name"]["type"] == "string"
    assert props["count"]["type"] == "integer"
    assert props["ratio"]["type"] == "number"
    assert props["flag"]["type"] == "boolean"
    assert props["items"]["type"] == "array"
    assert props["meta"]["type"] == "object"
    # required excludes optional which has default
    assert "name" in schema["required"]
    assert "optional" not in schema.get("required", [])


def test_generate_excludes_internal_params() -> None:
    def spell(
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None,
        on_update: Any | None,
        real_arg: str,
    ) -> str:
        return real_arg

    schema = generate_spell_schema(spell)
    assert "real_arg" in schema["properties"]
    assert "spell_cast_id" not in schema["properties"]
    assert "params" not in schema["properties"]
    assert "signal" not in schema["properties"]
    assert "on_update" not in schema["properties"]


def test_generate_with_any_type_fallback() -> None:
    def spell(spell_cast_id: str, data: Any) -> str:  # noqa: ANN401
        return str(data)

    schema = generate_spell_schema(spell)
    # Any without explicit type still produces a property
    assert "data" in schema["properties"]


def test_validate_string() -> None:
    schema = {"properties": {"name": {"type": "string"}}, "required": ["name"]}
    assert validate_spell_args(schema, {"name": "hello"}) == {"name": "hello"}
    with pytest.raises(ValidationError):
        validate_spell_args(schema, {})


def test_validate_integer_and_number() -> None:
    schema = {
        "properties": {"count": {"type": "integer"}, "ratio": {"type": "number"}},
        "required": ["count"],
    }
    result = validate_spell_args(schema, {"count": 5, "ratio": 3.14})
    assert result["count"] == 5
    assert result["ratio"] == 3.14


def test_validate_boolean() -> None:
    schema = {"properties": {"flag": {"type": "boolean"}}}
    assert validate_spell_args(schema, {"flag": True})["flag"] is True
    assert validate_spell_args(schema, {})["flag"] is None


def test_validate_array_and_object() -> None:
    schema = {
        "properties": {
            "items": {"type": "array"},
            "meta": {"type": "object"},
        }
    }
    result = validate_spell_args(schema, {"items": [1, 2], "meta": {"k": "v"}})
    assert result["items"] == [1, 2]
    assert result["meta"] == {"k": "v"}


def test_validate_optional_defaults_to_none() -> None:
    schema = {"properties": {"opt": {"type": "string"}}}
    result = validate_spell_args(schema, {})
    assert result["opt"] is None


def test_validate_unknown_type_fallback() -> None:
    schema = {"properties": {"mystery": {"type": "unknown"}}}
    # falls back to Any, accepts anything
    assert validate_spell_args(schema, {"mystery": 123})["mystery"] == 123
