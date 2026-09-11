from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)
from mvgeos_core.truncate import (
    DEFAULT_MAX_BYTES,
    MAX_FIND_ENTRIES,
    TruncationResult,
    format_size,
    truncate_head,
    truncation_details,
)

from coding_mvge.spells._ignore import IsExcluded, default_is_excluded

DEFAULT_FIND_LIMIT = 1000


def _find_matches(
    base: Path,
    pattern: str,
    limit: int,
    include_ignored: bool = False,
    is_excluded: IsExcluded = default_is_excluded,
) -> tuple[list[str], set[str]]:
    skipped: set[str] = set()
    matches: list[str] = []
    stack: list[Path] = [base]
    while stack and len(matches) < limit:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda e: (e.name.lower(), e.name))
        except OSError:
            continue
        for entry in entries:
            if len(matches) >= limit:
                break
            try:
                entry_is_dir = entry.is_dir()
            except OSError:
                continue
            if entry_is_dir:
                if not include_ignored and is_excluded(entry, True):
                    skipped.add(entry.name)
                    continue
                stack.append(entry)
                continue
            try:
                matched = entry.match(pattern)
            except ValueError:
                matched = False
            if matched:
                matches.append(str(entry))
    matches.sort(key=lambda m: Path(m).as_posix())
    return matches, skipped


async def find(
    pattern: str,
    path: str = ".",
    limit: int = DEFAULT_FIND_LIMIT,
    include_ignored: bool = False,
) -> SpellResult:
    """Find files matching a glob pattern, sorted by posix path.

    Owns recursion; list_files only lists a single directory.

    Args:
        pattern: Glob pattern to match (e.g. "*.py").
        path: Directory to search from. Explicit paths are always honored,
            even inside default-ignored directories.
        limit: Maximum number of results (default 1000).
        include_ignored: When True, descend into default-ignored
            directories (e.g. .venv, .git, __pycache__).
    """
    try:
        if limit <= 0:
            return SpellResult(
                spell_name="find",
                status=SpellStatus.ERROR,
                error_message=f"Invalid limit '{limit}'. Must be a positive number.",
            )
        effective_limit = min(limit, MAX_FIND_ENTRIES)
        base = Path(path)
        if not await asyncio.to_thread(base.exists):
            return SpellResult(
                spell_name="find",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        matches, skipped = await asyncio.to_thread(
            _find_matches, base, pattern, effective_limit, include_ignored
        )
        if not matches and not skipped:
            return SpellResult(
                spell_name="find",
                status=SpellStatus.SUCCESS,
                content="No files found matching pattern",
                details=truncation_details(
                    TruncationResult(
                        text="",
                        truncated=False,
                        strategy=None,
                        total_lines=0,
                        shown_start=None,
                        shown_end=None,
                        total_bytes=0,
                    )
                ),
            )
        notices: list[str] = []
        if skipped:
            names = ", ".join(sorted(skipped))
            notices.append(
                f"Skipped ignored directories: {names}. "
                "Re-call with include_ignored=True to include them."
            )
        if effective_limit < limit:
            notices.append(
                f"Limit capped at {MAX_FIND_ENTRIES} results. "
                "Use a narrower path for larger trees"
            )
        result_limit_reached = len(matches) >= effective_limit
        if result_limit_reached:
            notices.append(
                f"{effective_limit} results limit reached. "
                f"Re-call with limit={effective_limit * 2} for more, "
                "or refine pattern"
            )
        truncation = truncate_head("\n".join(matches))
        output = truncation.text
        if truncation.truncated:
            notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
        if notices:
            suffix = f"[{' '.join(notices)}]"
            output = f"{output}\n\n{suffix}" if output else " ".join(notices)
        return SpellResult(
            spell_name="find",
            status=SpellStatus.SUCCESS,
            content=output,
            details=truncation_details(truncation),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="find",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
