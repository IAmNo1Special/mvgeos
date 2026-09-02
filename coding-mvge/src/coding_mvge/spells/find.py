from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def find(pattern: str, path: str = ".") -> SpellResult:
    """Find files matching a glob pattern relative to a directory path."""
    try:
        base = Path(path)
        if not await asyncio.to_thread(base.exists):
            return SpellResult(
                spell_name="find",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        matches = await asyncio.to_thread(lambda: list(base.rglob(pattern)))
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
