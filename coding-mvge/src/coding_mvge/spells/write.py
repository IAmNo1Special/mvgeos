from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def cast_write(path: str, content: str) -> SpellResult:
    try:
        file_path = Path(path)
        await asyncio.to_thread(_write_file, file_path, content)
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
