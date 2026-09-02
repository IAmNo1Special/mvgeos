from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mvgeos_provider.types import AbortError, AbortSignal
from pydantic import BaseModel

from mvgeos_agent.errors import SpellDiscoveryError
from mvgeos_agent.spell_schema import generate_spell_schema
from mvgeos_agent.types import MvgeSpell, SpellExecutionMode, SpellResult

type SpellUnion = Callable[..., Any] | MvgeSpell


class FunctionSpell(MvgeSpell):
    """An executable MvgeSpell wrapping an arbitrary Python callable.

    Infers tool name from func.__name__, description from func.__doc__, and
    parameter JSON Schema via generate_spell_schema. Supports both async and
    sync callables, gracefully converting outputs into model-ready strings.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
        execution_mode: SpellExecutionMode = SpellExecutionMode.PARALLEL,
    ) -> None:
        func_name = (
            name if name is not None else getattr(func, "__name__", "custom_spell")
        )
        if not isinstance(func_name, str):
            func_name = str(func_name)
        doc = description
        if doc is None:
            raw_doc = getattr(func, "__doc__", "") or ""
            doc = inspect.cleandoc(raw_doc) if raw_doc else f"Execute {func_name}."
        schema = parameters if parameters is not None else generate_spell_schema(func)
        super().__init__(
            name=func_name,
            description=doc,
            parameters=schema,
            execution_mode=execution_mode,
        )
        self.func = func

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: AbortSignal | None = None,
        on_update: Any | None = None,
    ) -> str:
        if signal is not None and getattr(signal, "aborted", False):
            raise AbortError("Operation aborted")

        validated = self.prepare_arguments(params)
        args = {k: v for k, v in validated.items() if v is not None}

        if inspect.iscoroutinefunction(self.func):
            result = await self.func(**args)
        else:
            result = await asyncio.to_thread(self.func, **args)

        if isinstance(result, SpellResult):
            if result.error_message:
                return f"[error] {result.error_message}"
            return result.content or f"{self.name} completed"
        elif isinstance(result, str):
            return result
        elif isinstance(result, BaseModel):
            return result.model_dump_json()
        elif isinstance(result, (dict, list)):
            return json.dumps(result)
        elif result is None:
            return f"{self.name} completed"
        else:
            return str(result)


def coerce_spell(spell: Callable[..., Any] | MvgeSpell) -> MvgeSpell:
    """Coerce a callable or MvgeSpell instance into an executable MvgeSpell."""
    if isinstance(spell, MvgeSpell):
        return spell
    if callable(spell):
        return FunctionSpell(func=spell)
    raise TypeError(f"Expected Callable or MvgeSpell, got {type(spell).__name__}")


def discover_spells_from_dir(spells_dir: Path) -> list[MvgeSpell]:
    """Auto-discover spells from a spells/ directory.

    Discovery precedence:
    1. If `spells/__init__.py` defines `__all__`, load and coerce each listed attribute.
    2. Otherwise, scan all non-underscore `.py` files in alphabetical order:
       - Match a callable named after the file stem (e.g. `def bash(...)` in `bash.py`).
       - Fallback: Look for a single public function defined in that file.
       - If ambiguous or no candidate is found, raise `SpellDiscoveryError`.
    """
    if not spells_dir.is_dir():
        return []

    init_file = spells_dir / "__init__.py"
    if init_file.is_file():
        spec = importlib.util.spec_from_file_location(
            f"mvgeos_spells_{spells_dir.name}", init_file
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "__all__") and module.__all__:
                spells: list[MvgeSpell] = []
                for name in module.__all__:
                    if hasattr(module, name):
                        obj = getattr(module, name)
                        spells.append(coerce_spell(obj))
                    else:
                        raise SpellDiscoveryError(
                            f"Spell '{name}' listed in __all__ of '{init_file}' "
                            f"was not found in the module."
                        )
                return spells

    py_files = sorted(
        f
        for f in spells_dir.iterdir()
        if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
    )
    if not py_files:
        return []

    spells = []
    for py_file in py_files:
        module_name = f"mvgeos_spells_{spells_dir.name}_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 1. Match function name == py_file.stem
        if hasattr(module, py_file.stem):
            candidate = getattr(module, py_file.stem)
            if callable(candidate) or isinstance(candidate, MvgeSpell):
                spells.append(coerce_spell(candidate))
                continue

        # 2. Look for single public function defined in this file
        public_candidates: list[tuple[str, Any]] = []
        for attr_name, attr_val in inspect.getmembers(module):
            if attr_name.startswith("_"):
                continue
            is_valid_spell = isinstance(attr_val, MvgeSpell) or (
                callable(attr_val)
                and getattr(attr_val, "__module__", "") == module.__name__
            )
            if is_valid_spell:
                public_candidates.append((attr_name, attr_val))

        if len(public_candidates) == 1:
            spells.append(coerce_spell(public_candidates[0][1]))
        else:
            init_path = spells_dir / "__init__.py"
            raise SpellDiscoveryError(
                f"Could not discover spell in '{py_file.name}': No function "
                f"named '{py_file.stem}' found, and no '__all__' was defined "
                f"in '{init_path}'. Either define 'def {py_file.stem}(...)' "
                f"or export it in '__all__'."
            )

    return spells
