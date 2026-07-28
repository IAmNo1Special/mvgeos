from __future__ import annotations

from pathlib import Path

from mvgeos_spells.types import SpellResult, SpellStatus


async def cast_list(path: str = ".", recursive: bool = False) -> SpellResult:
    try:
        base = Path(path)
        if not base.exists():
            return SpellResult(
                spell_name="list",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        if recursive:
            items = sorted(str(p) for p in base.rglob("*") if p.is_file() or p.is_dir())
        else:
            items = sorted(str(p) for p in base.iterdir())
        return SpellResult(
            spell_name="list",
            status=SpellStatus.SUCCESS,
            content="\n".join(items),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="list",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
