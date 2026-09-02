from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_agent.types import SpellResult, SpellStatus


def _list_paths(base: Path, recursive: bool) -> list[str]:
    if not base.exists():
        raise FileNotFoundError(base)
    if recursive:
        items = sorted(str(p) for p in base.rglob("*") if p.is_file() or p.is_dir())
    else:
        items = sorted(str(p) for p in base.iterdir())
    return items


async def list_files(path: str = ".", recursive: bool = False) -> SpellResult:
    """List directory contents, optionally recursively."""
    try:
        base = Path(path)
        items = await asyncio.to_thread(_list_paths, base, recursive)
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.SUCCESS,
            content="\n".join(items),
        )
    except FileNotFoundError:
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.ERROR,
            error_message=f"Path not found: {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
