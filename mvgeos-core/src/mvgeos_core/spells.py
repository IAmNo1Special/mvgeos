from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError, create_model

from mvgeos_core.abort import AbortSignal


class ExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


SpellExecutionMode = ExecutionMode


class SpellStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


@dataclass
class SpellResult:
    spell_name: str
    status: SpellStatus = SpellStatus.SUCCESS
    content: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    terminate: bool = False


@dataclass
class SpellResultMessage:
    role: str = "spellResult"
    spell_cast_id: str = ""
    spell_name: str = ""
    content: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] | None = None
    is_error: bool = False
    timestamp: float = 0.0
    terminate: bool = False


class SpellSignal(Protocol):
    cancelled: bool

    def cancel(self) -> None: ...

    def raise_if_aborted(self) -> None: ...


SpellUpdateCallback = Callable[[dict[str, Any]], None]


@dataclass
class MvgeSpell:
    name: str
    description: str
    parameters: dict[str, Any]
    execution_mode: SpellExecutionMode = SpellExecutionMode.PARALLEL
    _schema_model: type[BaseModel] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.parameters:
            self._schema_model = create_model(
                f"{self.name}_Schema",
                **self._convert_to_model_fields(self.parameters),
            )

    def _convert_to_model_fields(self, params: dict[str, Any]) -> dict[str, Any]:
        """Convert JSON Schema properties to Pydantic model fields."""
        fields = {}
        props = params.get("properties", {})
        required = params.get("required", [])
        for name, prop in props.items():
            field_type = self._json_type_to_python(prop)
            # Use the field type directly; Pydantic infers optional from default
            fields[name] = (field_type, ... if name in required else None)
        return fields

    def _json_type_to_python(self, prop: dict[str, Any]) -> type:
        """Convert JSON Schema type to Python type."""
        json_type = prop.get("type")
        if not json_type and "anyOf" in prop:
            types = [
                t.get("type")
                for t in prop["anyOf"]
                if isinstance(t, dict) and t.get("type") != "null"
            ]
            if "integer" in types:
                return int
            if "number" in types:
                return float
            if "boolean" in types:
                return bool
            if "array" in types:
                return list[Any]
            if "object" in types:
                return dict[str, Any]
            json_type = "string"

        if json_type == "string":
            return str
        elif json_type == "integer":
            return int
        elif json_type == "number":
            return float
        elif json_type == "boolean":
            return bool
        elif json_type == "array":
            items = prop.get("items", {})
            if items:
                _ = self._json_type_to_python(items)
                # Use list[Any] and let Pydantic handle validation at runtime
                return list[Any]
            return list[Any]
        elif json_type == "object":
            return dict[str, Any]
        return Any

    def prepare_arguments(self, args: dict[str, Any]) -> dict[str, Any]:
        if self._schema_model is None:
            return args
        try:
            validated = self._schema_model.model_validate(args)
            return validated.model_dump()
        except ValidationError as e:
            raise ValueError(f"Invalid arguments for spell {self.name}: {e}") from e

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any] | str | SpellResult:
        raise NotImplementedError


__all__ = [
    "ExecutionMode",
    "MvgeSpell",
    "SpellExecutionMode",
    "SpellResult",
    "SpellResultMessage",
    "SpellSignal",
    "SpellStatus",
    "SpellUpdateCallback",
]
