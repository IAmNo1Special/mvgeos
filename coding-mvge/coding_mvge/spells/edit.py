from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


class _EditTargetNotFoundError(Exception):
    pass


def _edit_file(path: Path, old_string: str, new_string: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    content = path.read_text(encoding="utf-8")
    if old_string not in content:
        raise _EditTargetNotFoundError(old_string)
    path.write_text(content.replace(old_string, new_string), encoding="utf-8")


async def cast_edit(path: str, old_string: str, new_string: str) -> SpellResult:
    try:
        file_path = Path(path)
        await asyncio.to_thread(_edit_file, file_path, old_string, new_string)
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.SUCCESS,
            content=f"Updated {path}",
        )
    except _EditTargetNotFoundError:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=f"Old string not found in {path}",
        )
    except FileNotFoundError:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=f"File not found: {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="edit",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
