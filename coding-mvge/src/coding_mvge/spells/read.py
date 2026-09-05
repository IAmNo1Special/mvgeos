from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def read(path: str) -> SpellResult:
    """Read the contents of a file at the specified path."""
    try:
        file_path = Path(path)
        if await asyncio.to_thread(file_path.is_dir):
            skill_md = file_path / "SKILL.md"
            if await asyncio.to_thread(skill_md.is_file):
                file_path = skill_md
        if not await asyncio.to_thread(file_path.exists):
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"File not found: {path}",
            )
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")

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
