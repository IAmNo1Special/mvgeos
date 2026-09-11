from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)
from mvgeos_core.truncate import (
    DEFAULT_MAX_BYTES,
    MAX_LIST_ENTRIES,
    MAX_LIST_RESULTS,
    TruncationResult,
    format_size,
    truncate_head,
    truncation_details,
)


def _list_entries(base: Path) -> list[str]:
    if not base.exists():
        raise FileNotFoundError(base)
    if not base.is_dir():
        raise NotADirectoryError(base)
    entries = sorted(base.iterdir(), key=lambda e: (e.name.lower(), e.name))
    results: list[str] = []
    for entry in entries:
        try:
            suffix = "/" if entry.is_dir() else ""
        except OSError:
            continue
        results.append(f"{entry}{suffix}")
    return results


def _empty_details() -> dict[str, object]:
    return truncation_details(
        TruncationResult(
            text="",
            truncated=False,
            strategy=None,
            total_lines=0,
            shown_start=None,
            shown_end=None,
            total_bytes=0,
        )
    )


async def list_files(
    path: str = ".", limit: int = MAX_LIST_RESULTS, include_ignored: bool = False
) -> SpellResult:
    """List directory contents, sorted alphabetically with '/' for dirs.

    Only lists a single directory; use find with '*' to recurse.

    Args:
        path: The directory path to list. Explicit paths are always
            honored, even inside default-ignored directories.
        limit: Maximum number of entries (default 500).
        include_ignored: Reserved for find-style recursion; single-dir
            listings always show direct children.
    """
    try:
        if limit <= 0:
            return SpellResult(
                spell_name="list_files",
                status=SpellStatus.ERROR,
                error_message=f"Invalid limit '{limit}'. Must be a positive number.",
            )
        effective_limit = min(limit, MAX_LIST_ENTRIES)
        base = Path(path)
        items = await asyncio.to_thread(_list_entries, base)
        if not items:
            return SpellResult(
                spell_name="list_files",
                status=SpellStatus.SUCCESS,
                content="(empty directory)",
                details=_empty_details(),
            )
        notices: list[str] = []
        if effective_limit < limit:
            notices.append(
                f"Limit capped at {MAX_LIST_ENTRIES} entries. "
                "Use find with a narrower path for larger trees"
            )
        entry_limit_reached = len(items) > effective_limit
        shown = items[:effective_limit]
        if entry_limit_reached:
            notices.append(
                f"{effective_limit} entries limit reached. "
                f"Re-call with limit={effective_limit * 2} for more"
            )
        truncation = truncate_head("\n".join(shown))
        output = truncation.text
        if truncation.truncated:
            notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
        if notices:
            output += f"\n\n[{' '.join(notices)}]"
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.SUCCESS,
            content=output,
            details=truncation_details(truncation),
        )
    except FileNotFoundError:
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.ERROR,
            error_message=f"Path not found: {path}",
        )
    except NotADirectoryError:
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.ERROR,
            error_message=f"Not a directory: {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="list_files",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
