from __future__ import annotations

from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def cast_write(path: str, content: str) -> SpellResult:
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return SpellResult(
            spell_name="write",
            status=SpellStatus.SUCCESS,
            content=f"Wrote to {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="write",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
