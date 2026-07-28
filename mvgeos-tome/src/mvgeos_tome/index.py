from __future__ import annotations

from collections.abc import Generator

from mvgeos_tome.types import TomeEntry, TomeEntryType


class Index:
    def __init__(self) -> None:
        self._entries_by_id: dict[str, TomeEntry] = {}
        self._entries_by_parent: dict[str | None, list[str]] = {}
        self._leaf_ids: list[str] = []

    def add(self, entry: TomeEntry) -> None:
        self._entries_by_id[entry.id] = entry
        parent_id = entry.parent_id
        if parent_id not in self._entries_by_parent:
            self._entries_by_parent[parent_id] = []
        self._entries_by_parent[parent_id].append(entry.id)
        if entry.type == TomeEntryType.LEAF:
            self._leaf_ids.append(entry.id)

    def get(self, entry_id: str) -> TomeEntry | None:
        return self._entries_by_id.get(entry_id)

    def children(self, parent_id: str | None) -> Generator[TomeEntry]:
        entry_ids = self._entries_by_parent.get(parent_id, [])
        for eid in entry_ids:
            entry = self._entries_by_id.get(eid)
            if entry is not None:
                yield entry

    def leaves(self) -> Generator[TomeEntry]:
        for lid in self._leaf_ids:
            entry = self._entries_by_id.get(lid)
            if entry is not None:
                yield entry

    def all(self) -> Generator[TomeEntry]:
        yield from self._entries_by_id.values()
