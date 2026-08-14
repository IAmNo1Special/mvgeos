from __future__ import annotations

import asyncio
import re
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def cast_grep(
    pattern: str, path: str, output_mode: str = "content"
) -> SpellResult:
    try:
        file_path = Path(path)
        exists = await asyncio.to_thread(file_path.exists)
        if not exists:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        is_file = await asyncio.to_thread(file_path.is_file)
        if not is_file:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.SUCCESS,
                content="",
            )
        text = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        regex = re.compile(pattern)
        matches: list[str] = []
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append(f"{i}: {line}" if output_mode == "content" else str(i))
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.SUCCESS,
            content="\n".join(matches),
        )
    except re.error as exc:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
