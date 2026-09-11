from __future__ import annotations

import asyncio
from pathlib import Path

from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)
from mvgeos_core.truncate import (
    DEFAULT_MAX_BYTES,
    GREP_MAX_LINE_LENGTH,
    format_size,
    truncate_head,
    truncation_details,
)

_BINARY_PROBE_BYTES = 8192


def _split_file_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return lines


async def read(
    path: str, offset: int | None = None, limit: int | None = None
) -> SpellResult:
    """Read file contents with line pagination and bounded output.

    Output is truncated to 2000 lines or 50.0KB (whichever first); use
    offset/limit to page through large files.

    Args:
        path: The file path to read.
        offset: Line number to start reading from (1-indexed).
        limit: Maximum number of lines to read from the offset.
    """
    try:
        if offset is not None and offset < 1:
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"Invalid offset '{offset}'. Must be 1 or greater.",
            )
        if limit is not None and limit < 1:
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"Invalid limit '{limit}'. Must be 1 or greater.",
            )
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

        def _read_bytes() -> bytes:
            with open(file_path, "rb") as handle:
                return handle.read()

        raw = await asyncio.to_thread(_read_bytes)
        if b"\x00" in raw[:_BINARY_PROBE_BYTES]:
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"Binary file not supported: {path}",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=f"Binary file not supported: {path}",
            )
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = _split_file_lines(text)
        total = len(lines)
        start = (offset or 1) - 1
        if start >= total:
            return SpellResult(
                spell_name="read",
                status=SpellStatus.ERROR,
                error_message=(
                    f"Offset {offset} is beyond end of file ({total} lines total)"
                ),
            )
        window = lines[start:]
        user_capped = False
        if limit is not None and len(window) > limit:
            window = window[:limit]
            user_capped = True
        truncation = truncate_head("\n".join(window))
        display_start = start + 1
        if truncation.truncated and not truncation.text:
            first_size = format_size(len(lines[start].encode("utf-8")))
            head = lines[start][:GREP_MAX_LINE_LENGTH]
            return SpellResult(
                spell_name="read",
                status=SpellStatus.SUCCESS,
                content=(
                    f"{head}...\n\n[Line {display_start} is {first_size}, exceeds "
                    f"{format_size(DEFAULT_MAX_BYTES)} limit. "
                    "Showing first 500 chars.]"
                ),
                details=truncation_details(truncation),
            )
        if truncation.truncated and truncation.shown_end is not None:
            display_end = start + truncation.shown_end
            return SpellResult(
                spell_name="read",
                status=SpellStatus.SUCCESS,
                content=(
                    f"{truncation.text}\n\n[Showing lines "
                    f"{display_start}-{display_end} of {total} "
                    f"({format_size(DEFAULT_MAX_BYTES)} / 2000-line cap). "
                    f"Use offset={display_end + 1} to continue.]"
                ),
                details=truncation_details(truncation),
            )
        if user_capped:
            consumed = start + len(window)
            remaining = total - consumed
            return SpellResult(
                spell_name="read",
                status=SpellStatus.SUCCESS,
                content=(
                    f"{truncation.text}\n\n[{remaining} more lines in file. "
                    f"Use offset={consumed + 1} to continue.]"
                ),
                details=truncation_details(truncation),
            )
        return SpellResult(
            spell_name="read",
            status=SpellStatus.SUCCESS,
            content=truncation.text,
            details=truncation_details(truncation),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="read",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
