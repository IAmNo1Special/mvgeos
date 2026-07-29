from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mvgeos_tome.types import TomeEntry


class JsonlStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def append(self, entry: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def read_entries(self) -> list[TomeEntry]:
        from mvgeos_tome.types import TomeEntryType

        entries: list[TomeEntry] = []
        for raw in self.read_all():
            entry = TomeEntry(
                id=raw["id"],
                parent_id=raw.get("parentId"),
                type=TomeEntryType(raw["type"]),
                timestamp=raw["timestamp"],
                payload=raw.get("payload", {}),
            )
            entries.append(entry)
        return entries
