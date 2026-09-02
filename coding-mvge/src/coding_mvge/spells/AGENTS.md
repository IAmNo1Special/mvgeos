# Spells Specification & Authoring Guide

Spells are native Python callables or `MvgeSpell` classes that provide the agent with deterministic tools.

## Structure & Conventions
- Place each spell in its own module: `spells/<spell_name>.py`.
- The main entry point function must match the file stem: `def <spell_name>(...) -> SpellResult | str:`.
- Use type annotations for all arguments and return types.
- Provide a clean Google-style docstring explaining purpose and parameters (`Args:`).
- Re-export the spell in `spells/__init__.py` and include it in `__all__`.

## Example Spell Template
```python
from __future__ import annotations
from mvgeos_agent.types import SpellResult, SpellStatus


async def my_spell(target: str, count: int = 1) -> SpellResult:
    """Perform a custom operation on a target.

    Args:
        target: The target identifier to process.
        count: Number of iterations.
    """
    try:
        # Perform action
        return SpellResult(
            spell_name="my_spell",
            status=SpellStatus.SUCCESS,
            content=f"Processed {target} x{count}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="my_spell",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
```
