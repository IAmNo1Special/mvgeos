from __future__ import annotations

import json
from pathlib import Path

from mvgeos_tome.index import Index
from mvgeos_tome.jsonl_store import JsonlStore
from mvgeos_tome.locking import FileLock
from mvgeos_tome.types import TomeEntry, TomeEntryType, TomeMetadata


class TomeLedger:
    def __init__(self, tome_dir: Path) -> None:
        self._tome_dir = tome_dir
        self._entries_dir = tome_dir / "entries"
        self._index_path = tome_dir / "index.json"
        self._index = Index()
        self._tomles: dict[str, TomeMetadata] = {}
        self._lock = FileLock(str(tome_dir / ".lock"), timeout=30.0)

    @property
    def dir(self) -> Path:
        return self._tome_dir

    def create_tome(self, metadata: TomeMetadata) -> TomeMetadata:
        with self._lock:
            self._tomles[metadata.id] = metadata
            self._entries_dir.mkdir(parents=True, exist_ok=True)
            (self._entries_dir / f"{metadata.id}.jsonl").write_text(
                "", encoding="utf-8"
            )
            self._save_index()
        return metadata

    def open_tome(self, tome_id: str) -> TomeMetadata | None:
        with self._lock:
            meta = self._tomles.get(tome_id)
            if meta is None:
                meta = self._load_metadata(tome_id)
            return meta

    def append(self, tome_id: str, entry: TomeEntry) -> None:
        with self._lock:
            store = JsonlStore(self._entries_dir / f"{tome_id}.jsonl")
            store.append(entry.__dict__)
            self._index.add(entry)
            self._save_index()

    def get_entries(
        self,
        tome_id: str,
        entry_type: TomeEntryType | None = None,
        limit: int | None = None,
    ) -> list[TomeEntry]:
        with self._lock:
            store = JsonlStore(self._entries_dir / f"{tome_id}.jsonl")
            entries = store.read_entries()
            if entry_type is not None:
                entries = [e for e in entries if e.type == entry_type]
            if limit is not None:
                entries = entries[-limit:]
            return entries

    def get_leaf_id(self, tome_id: str) -> str | None:
        with self._lock:
            for entry in self._index.leaves():
                if entry.id.startswith(f"{tome_id}_"):
                    return entry.id
            return None

    def _load_metadata(self, tome_id: str) -> TomeMetadata | None:
        meta_path = self._tome_dir / f"{tome_id}.meta.json"
        if not meta_path.exists():
            return None
        with meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return TomeMetadata(**data)

    def _save_index(self) -> None:
        with self._index_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "entries": [
                        {
                            "id": e.id,
                            "parent_id": e.parent_id,
                            "type": e.type.value,
                            "timestamp": e.timestamp,
                        }
                        for e in self._index.all()
                    ],
                },
                f,
                indent=2,
            )
