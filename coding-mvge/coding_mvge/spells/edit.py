from __future__ import annotations

from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def cast_edit(path: str, old_string: str, new_string: str) -> SpellResult:
    try:
        file_path = Path(path)
        if not file_path.exists():
            return SpellResult(
                spell_name="edit",
                status=SpellStatus.ERROR,
                error_message=f"File not found: {path}",
            )
        content = file_path.read_text(encoding="utf-8")
        if old_string not in content:
            return SpellResult(
                spell_name="edit",
                status=SpellStatus.ERROR,
                error_message=f"Old string not found in {path}",
            )
        new_content = content.replace(old_string, new_string)
        file_path.write_text(new_content, encoding="utf-8")
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.SUCCESS,
            content=f"Updated {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
