"""Tome service layer for MvgeOS GUI.

Handles session indexing, timestamps, and git branch resolution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mvgeos_core.constants import DEFAULT_TOME_DIR
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeEntryType

from mvgeos_gui.git_workspace import resolve_git_branch


@dataclass
class TomeListEntry:
    """A Tome entry for display in the sidebar tome list."""

    tome_id: str
    title: str
    created_at: str
    relative_time: str
    git_branch: str | None
    is_active: bool = False


def format_relative_time(timestamp_str: str) -> str:
    """Format an ISO 8601 timestamp as a human-readable relative time string.

    Returns values like "now", "17m", "1h", "2d".
    """
    dt = datetime.fromisoformat(timestamp_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    delta_seconds = (now - dt).total_seconds()

    if delta_seconds < 60:
        return "now"
    minutes = int(delta_seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = int(delta_seconds // 3600)
    if hours < 24:
        return f"{hours}h"
    days = int(delta_seconds // 86400)
    return f"{days}d"


class TomeService:
    """Service for indexing and managing Tomes within the GUI."""

    def __init__(self, tome_dir: Path | None = None) -> None:
        self._tome_dir = tome_dir or DEFAULT_TOME_DIR
        self._ledger: TomeLedger | None = None

    @property
    def tome_dir(self) -> Path:
        return self._tome_dir

    @property
    def ledger(self) -> TomeLedger:
        if self._ledger is None:
            self._tome_dir.mkdir(parents=True, exist_ok=True)
            self._ledger = TomeLedger(self._tome_dir)
        return self._ledger

    def list_tomes_for_project(
        self, project_path: Path, active_tome_id: str | None = None
    ) -> list[TomeListEntry]:
        """List all Tomes for a project workspace, sorted newest-first."""
        ledger = self.ledger
        entries: list[TomeListEntry] = []
        norm_project = os.path.normcase(os.path.normpath(str(project_path)))
        for meta in ledger.list_tomes():
            tome_cwd = os.path.normcase(os.path.normpath(meta.cwd))
            if tome_cwd != norm_project:
                continue
            branch = resolve_git_branch(meta.cwd)
            title = self.get_tome_title(meta.id)
            entries.append(
                TomeListEntry(
                    tome_id=meta.id,
                    title=title,
                    created_at=meta.created_at,
                    relative_time=format_relative_time(meta.created_at),
                    git_branch=branch,
                    is_active=meta.id == active_tome_id,
                )
            )
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    def get_tome_title(self, tome_id: str) -> str:
        """Extract a human-readable title for a Tome.

        Looks for a TOME_INFO entry with a 'name' or 'title' field in its
        payload. Falls back to "Conversation" if none is found.
        """
        try:
            entries = self.ledger.get_entries(tome_id)
        except (ValueError, KeyError):
            return "Conversation"
        for entry in entries:
            if entry.type == TomeEntryType.TOME_INFO:
                payload = entry.payload
                if "name" in payload:
                    return str(payload["name"])
                if "title" in payload:
                    return str(payload["title"])
        return "Conversation"
