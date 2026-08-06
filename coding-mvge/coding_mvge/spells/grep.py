from __future__ import annotations

import re
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


async def cast_grep(
    pattern: str, path: str, output_mode: str = "content"
) -> SpellResult:
    try:
        file_path = Path(path)
        if not file_path.exists():
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        regex = re.compile(pattern)
        matches: list[str] = []
        if file_path.is_file():
            for i, line in enumerate(
                file_path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if regex.search(line):
                    matches.append(
                        f"{i}: {line}" if output_mode == "content" else str(i)
                    )
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.SUCCESS,
            content="\n".join(matches),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
