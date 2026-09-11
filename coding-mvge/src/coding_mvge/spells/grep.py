from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TypedDict

from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)
from mvgeos_core.truncate import (
    DEFAULT_MAX_BYTES,
    GREP_MAX_LINE_LENGTH,
    MAX_GREP_MATCHES,
    format_size,
    truncate_head,
    truncate_line_around_match,
    truncation_details,
)

from coding_mvge.spells._ignore import IsExcluded, default_is_excluded

_BINARY_PROBE_BYTES = 8192


class _GrepRecord(TypedDict):
    path: str
    sort_key: tuple[str, int]
    lineno: int
    line: str
    spans: list[tuple[int, int]]
    before: list[tuple[int, str]]
    after: list[tuple[int, str]]


def _iter_files(
    base: Path,
    include_ignored: bool,
    skipped: set[str],
    is_excluded: IsExcluded = default_is_excluded,
) -> list[Path]:
    files: list[Path] = []
    stack: list[Path] = [base]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda e: (e.name.lower(), e.name))
        except OSError:
            continue
        for entry in entries:
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
            files.append(entry)
    return files


def _read_lines(path: Path) -> list[str] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:_BINARY_PROBE_BYTES]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _collect_matches(
    base: Path,
    regex: re.Pattern[str],
    glob: str | None,
    context: int,
    limit: int,
    include_ignored: bool,
    is_excluded: IsExcluded,
) -> tuple[list[_GrepRecord], set[str], bool]:
    skipped: set[str] = set()
    records: list[_GrepRecord] = []
    acc_bytes = 0
    byte_budget = DEFAULT_MAX_BYTES
    byte_capped = False
    if base.is_file():
        candidates = [base]
    elif base.is_dir():
        candidates = _iter_files(base, include_ignored, skipped, is_excluded)
    else:
        raise FileNotFoundError(base)
    for candidate in candidates:
        if len(records) >= limit or acc_bytes > byte_budget:
            byte_capped = byte_capped or acc_bytes > byte_budget
            break
        if glob is not None:
            try:
                if not candidate.match(glob):
                    continue
            except ValueError:
                continue
        lines = _read_lines(candidate)
        if lines is None:
            continue
        path_str = str(candidate)
        for lineno, line in enumerate(lines, 1):
            spans = [match.span() for match in regex.finditer(line)]
            if not spans:
                continue
            if len(records) >= limit or acc_bytes > byte_budget:
                byte_capped = True
                break
            start = max(1, lineno - context)
            end = min(len(lines), lineno + context)
            records.append(
                {
                    "path": path_str,
                    "sort_key": (candidate.as_posix(), lineno),
                    "lineno": lineno,
                    "line": line,
                    "spans": spans,
                    "before": [(no, lines[no - 1]) for no in range(start, lineno)],
                    "after": [(no, lines[no - 1]) for no in range(lineno + 1, end + 1)],
                }
            )
            acc_bytes += len(line.encode("utf-8")) + 64
    records.sort(key=lambda r: (r["sort_key"], r["lineno"]))
    return records, skipped, byte_capped


def _cap_line(line: str, spans: list[tuple[int, int]]) -> tuple[str, bool]:
    if len(line) <= GREP_MAX_LINE_LENGTH:
        return line, False
    return truncate_line_around_match(line, spans), True


def _format_records(records: list[_GrepRecord], context: int) -> tuple[str, bool]:
    lines_truncated = False
    out: list[str] = []
    index = 0
    while index < len(records):
        path = records[index]["path"]
        group: list[_GrepRecord] = []
        while index < len(records) and records[index]["path"] == path:
            group.append(records[index])
            index += 1
        kinds: dict[int, str] = {}
        texts: dict[int, str] = {}
        spans: dict[int, list[tuple[int, int]]] = {}
        for record in group:
            lineno = record["lineno"]
            for no, text in record["before"]:
                texts.setdefault(no, text)
                kinds.setdefault(no, "ctx")
            texts[lineno] = record["line"]
            kinds[lineno] = "match"
            spans[lineno] = record["spans"]
            for no, text in record["after"]:
                texts.setdefault(no, text)
                kinds.setdefault(no, "ctx")
        for no in sorted(kinds):
            if kinds[no] == "match":
                capped, cut = _cap_line(texts[no], spans[no])
                lines_truncated = lines_truncated or cut
                out.append(f"{path}:{no}: {capped}")
            else:
                capped, cut = _cap_line(texts[no], [])
                lines_truncated = lines_truncated or cut
                out.append(f"{path}-{no}- {capped}")
    return "\n".join(out), lines_truncated


async def grep(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    ignore_case: bool = False,
    literal: bool = False,
    context: int = 0,
    limit: int = MAX_GREP_MATCHES,
    include_ignored: bool = False,
) -> SpellResult:
    """Search file contents for a pattern across files and directories.

    Respects default-ignored directories unless include_ignored is True.
    Output is capped at `limit` matches; long lines are windowed to
    500 chars around the match.

    Args:
        pattern: Search pattern (regex, or literal with literal=True).
        path: File or directory to search. Explicit paths are always
            honored, even inside default-ignored directories.
        glob: Optional glob to filter files (e.g. "*.py").
        ignore_case: Case-insensitive search.
        literal: Treat pattern as a literal string, not regex.
        context: Lines of context to show around each match.
        limit: Maximum number of matches (default 100).
        include_ignored: Descend into default-ignored directories.
    """
    try:
        if limit <= 0:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=f"Invalid limit '{limit}'. Must be a positive number.",
            )
        if context < 0:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=f"Invalid context '{context}'. Must be 0 or greater.",
            )
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(re.escape(pattern) if literal else pattern, flags)
        except re.error as exc:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=str(exc),
            )
        base = Path(path)
        if not await asyncio.to_thread(base.exists):
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.ERROR,
                error_message=f"Path not found: {path}",
            )
        records, skipped, _ = await asyncio.to_thread(
            _collect_matches,
            base,
            regex,
            glob,
            context,
            limit,
            include_ignored,
            default_is_excluded,
        )
        if not records:
            return SpellResult(
                spell_name="grep",
                status=SpellStatus.SUCCESS,
                content="No matches found",
                details=truncation_details(
                    truncate_head("", max_lines=1 << 60, max_bytes=1 << 60)
                ),
            )
        raw_output, lines_truncated = _format_records(records, context)
        truncation = truncate_head(raw_output)
        output = truncation.text
        notices: list[str] = []
        if len(records) >= limit:
            notices.append(
                f"{limit} matches limit reached. "
                f"Re-call with limit={limit * 2} for more, or refine pattern"
            )
        if truncation.truncated:
            notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
        if lines_truncated:
            notices.append(
                f"Some lines truncated to {GREP_MAX_LINE_LENGTH} chars. "
                "Use read tool to see full lines"
            )
        if skipped:
            names = ", ".join(sorted(skipped))
            notices.append(
                f"Skipped ignored directories: {names}. "
                "Re-call with include_ignored=True to include them."
            )
        if notices:
            output += f"\n\n[{' '.join(notices)}]"
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.SUCCESS,
            content=output,
            details=truncation_details(truncation),
        )
    except FileNotFoundError:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=f"Path not found: {path}",
        )
    except Exception as exc:
        return SpellResult(
            spell_name="grep",
            status=SpellStatus.ERROR,
            error_message=str(exc),
        )
