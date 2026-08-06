from __future__ import annotations

from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def cast_find(pattern: str, path: str = ".") -> SpellResult:
    try:
        base = Path(path)
        if not base.exists():
            return SpellResult(
                spell_name="find",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        matches = list(base.rglob(pattern))
        return SpellResult(
            spell_name="find",
            status=SpellStatus.SUCCESS,
            content="\n".join(str(m) for m in matches),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="find",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
