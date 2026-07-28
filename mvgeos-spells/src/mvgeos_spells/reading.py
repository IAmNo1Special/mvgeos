from __future__ import annotations

from pathlib import Path

from mvgeos_spells.types import SpellResult, SpellStatus


async def cast_read(path: str) -> SpellResult:
    try:
        file_path = Path(path)
        if not file_path.exists():
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"File not found: {path}",
            )
        content = file_path.read_text(encoding="utf-8")
        return SpellResult(
            spell_name="read",
            status=SpellStatus.SUCCESS,
            content=content,
        )
    except Exception as exc:
        return SpellResult(
            spell_name="read",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
