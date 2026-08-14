from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mvgeos_tome.locking import FileLock
from mvgeos_tome.types import TomeEntry, TomeEntryType, TomeMetadata


def _generate_short_id() -> str:
    return uuid.uuid4().hex[:8]


def _generate_id() -> str:
    return uuid.uuid4().hex


def _timestamp_now() -> float:
    return datetime.now(UTC).timestamp()


def _timestamp_iso() -> str:
    return datetime.now(UTC).isoformat()


class TomeLedger:
    _MAX_CACHE_SIZE = 32

    def __init__(self, tome_dir: Path) -> None:
        self._tome_dir = tome_dir
        self._tomles: dict[str, TomeMetadata] = {}
        self._entries_cache: OrderedDict[str, list[TomeEntry]] = OrderedDict()
        self._lock = FileLock(tome_dir / ".lock", timeout=30.0)
        self._load_tome_headers()

    def _resolve_tome_id(self, tome_id: str) -> str | None:
        if not tome_id:
            return None
        if tome_id in self._tomles:
            return tome_id
        exact_matches = [k for k in self._tomles if k.lower() == tome_id.lower()]
        if len(exact_matches) == 1:
            return exact_matches[0]
        prefix_matches = [
            k for k in self._tomles if k.lower().startswith(tome_id.lower())
        ]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        return None

    @property
    def dir(self) -> Path:
        return self._tome_dir

    def tome_file(self, tome_id: str) -> Path:
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            return self._tome_dir / f"{resolved_id}.jsonl"

    def list_tomes(self) -> list[TomeMetadata]:
        with self._lock:
            return list(self._tomles.values())

    def create_tome(
        self,
        metadata_or_cwd: TomeMetadata | str,
        parent_tome_id: str | None = None,
        tome_id: str | None = None,
    ) -> TomeMetadata:
        with self._lock:
            if isinstance(metadata_or_cwd, TomeMetadata):
                metadata = metadata_or_cwd
                metadata.schema_version = "1.0"
                tome_id = metadata.id
            else:
                tome_id = tome_id or _generate_id()
                timestamp = _timestamp_iso()
                metadata = TomeMetadata(
                    id=tome_id,
                    created_at=timestamp,
                    cwd=metadata_or_cwd,
                    parent_tome_id=parent_tome_id,
                    active_leaf_id=None,
                    schema_version="1.0",
                )

            self._tomles[tome_id] = metadata
            self._write_tome_file(metadata, [])
            return metadata

    def open_tome(self, tome_id: str) -> TomeMetadata | None:
        with self._lock:
            meta = self._tomles.get(tome_id)
            if meta is None and Path(tome_id).is_file():
                meta = self._load_tome_metadata(Path(tome_id))
                if meta:
                    self._tomles[meta.id] = meta
            if meta is None:
                meta = self._load_tome_metadata(tome_id)
                if meta:
                    self._tomles[meta.id] = meta
            if meta is None:
                resolved_id = self._resolve_tome_id(tome_id) or self._resolve_tome_id(
                    Path(tome_id).stem
                )
                if resolved_id:
                    meta = self._tomles.get(resolved_id)
            return meta

    def open_recent(self, cwd: str) -> TomeMetadata | None:
        with self._lock:
            if not self._tome_dir.exists():
                return None
            tome_files = sorted(self._tome_dir.glob("*.jsonl"), reverse=True)
            for f in tome_files:
                try:
                    meta = self._load_tome_metadata(f.stem)
                    if meta and meta.cwd == cwd:
                        return meta
                except json.JSONDecodeError, ValueError:
                    continue
            return None

    def append(self, tome_id: str, entry: TomeEntry) -> None:
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            metadata = self._tomles.get(resolved_id)
            if metadata is None:
                metadata = self._load_tome_metadata(resolved_id)
                if metadata is None:
                    raise ValueError(f"Tome not found: {tome_id}")

            self._append_entry_to_file(resolved_id, entry)
            self._invalidate_cache(resolved_id)

    def _invalidate_cache(self, tome_id: str | None) -> None:
        if tome_id is not None and tome_id in self._entries_cache:
            del self._entries_cache[tome_id]

    def append_message(
        self,
        tome_id: str,
        role: str,
        content: Any,
        parent_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> TomeEntry:
        entry = TomeEntry(
            id=_generate_short_id(),
            parent_id=parent_id,
            type=TomeEntryType.MESSAGE,
            timestamp=_timestamp_now(),
            payload={
                "role": role,
                "content": content,
                "model": model,
                "provider": provider,
            },
        )
        self.append(tome_id, entry)
        return entry

    def append_leaf(self, tome_id: str, target_id: str) -> TomeEntry:
        entry = TomeEntry(
            id=_generate_short_id(),
            parent_id=None,
            type=TomeEntryType.LEAF,
            timestamp=_timestamp_now(),
            payload={"targetId": target_id},
        )
        self.append(tome_id, entry)
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            metadata = self._tomles[resolved_id]
            metadata.active_leaf_id = target_id
            self._write_tome_file(metadata, self._read_tome_entries(resolved_id))
        return entry

    def append_custom(
        self,
        tome_id: str,
        payload: dict[str, Any],
        parent_id: str | None = None,
    ) -> TomeEntry:
        entry = TomeEntry(
            id=_generate_short_id(),
            parent_id=parent_id,
            type=TomeEntryType.CUSTOM,
            timestamp=_timestamp_now(),
            payload=payload,
        )
        self.append(tome_id, entry)
        return entry

    def append_tome_info(self, tome_id: str, payload: dict[str, Any]) -> TomeEntry:
        entry = TomeEntry(
            id=_generate_short_id(),
            parent_id=None,
            type=TomeEntryType.TOME_INFO,
            timestamp=_timestamp_now(),
            payload=payload,
        )
        self.append(tome_id, entry)
        return entry

    def append_label(
        self, tome_id: str, label: str, parent_id: str | None = None
    ) -> TomeEntry:
        entry = TomeEntry(
            id=_generate_short_id(),
            parent_id=parent_id,
            type=TomeEntryType.LABEL,
            timestamp=_timestamp_now(),
            payload={"label": label},
        )
        self.append(tome_id, entry)
        return entry

    def append_compaction(
        self, tome_id: str, payload: dict[str, Any], parent_id: str | None = None
    ) -> TomeEntry:
        entry = TomeEntry(
            id=_generate_short_id(),
            parent_id=parent_id,
            type=TomeEntryType.COMPACTION,
            timestamp=_timestamp_now(),
            payload=payload,
        )
        self.append(tome_id, entry)
        return entry

    def get_entries(
        self,
        tome_id: str,
        entry_type: TomeEntryType | None = None,
        limit: int | None = None,
    ) -> list[TomeEntry]:
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            entries = self._read_tome_entries(resolved_id)
            if entry_type is not None:
                entries = [e for e in entries if e.type == entry_type]
            if limit is not None:
                entries = entries[-limit:]
            return entries

    def get_entry(self, tome_id: str, entry_id: str) -> TomeEntry | None:
        # Entry ids are short and only unique within a Tome, and the index
        # spans every Tome, so scope the lookup to this Tome's own entries.
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            for entry in self._read_tome_entries(resolved_id):
                if entry.id == entry_id:
                    return entry
            return None

    def get_leaf_id(self, tome_id: str) -> str | None:
        """The entry the Tome's Leaf currently points at."""
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            for entry in reversed(self._read_tome_entries(resolved_id)):
                if entry.type == TomeEntryType.LEAF:
                    target = entry.payload.get("targetId")
                    return str(target) if target is not None else None
            meta = self._tomles.get(resolved_id) or self._load_tome_metadata(
                resolved_id
            )
            if meta and meta.active_leaf_id:
                return meta.active_leaf_id
            return None

    def create_branched_tome(
        self,
        parent_tome_id: str,
        cwd: str,
        fork_from_leaf_id: str | None = None,
        tome_id: str | None = None,
    ) -> TomeMetadata:
        with self._lock:
            resolved_parent_id = self._resolve_tome_id(parent_tome_id) or parent_tome_id
            parent_meta = self._tomles.get(
                resolved_parent_id
            ) or self._load_tome_metadata(resolved_parent_id)
            if parent_meta is None:
                raise ValueError(f"Parent tome not found: {parent_tome_id}")

            new_tome_id = tome_id or _generate_id()
            metadata = TomeMetadata(
                id=new_tome_id,
                created_at=_timestamp_iso(),
                cwd=parent_meta.cwd,
                parent_tome_id=parent_meta.id,
                active_leaf_id=fork_from_leaf_id,
                schema_version="1.0",
            )
            self._tomles[new_tome_id] = metadata

            parent_entries = self._read_tome_entries(parent_meta.id)
            if fork_from_leaf_id:
                parent_entries = self._filter_entries_to_leaf(
                    parent_entries, fork_from_leaf_id
                )

            self._write_tome_file(metadata, parent_entries)
            self._invalidate_cache(new_tome_id)
            return metadata

    def get_entries_for_context(
        self,
        tome_id: str,
        leaf_id: str | None = None,
        max_entries: int | None = None,
    ) -> list[TomeEntry]:
        with self._lock:
            resolved_id = self._resolve_tome_id(tome_id) or tome_id
            entries = self.get_entries(resolved_id)
            if leaf_id:
                entries = self._filter_entries_to_leaf(entries, leaf_id)
            if max_entries is not None:
                entries = entries[-max_entries:]
            return entries

    def _tome_file_path(self, tome_id: str) -> Path:
        resolved_id = self._resolve_tome_id(tome_id) or tome_id
        return self._tome_dir / f"{resolved_id}.jsonl"

    def _append_entry_to_file(self, tome_id: str, entry: TomeEntry) -> None:
        tome_file = self._tome_file_path(tome_id)
        line = json.dumps(
            {
                "id": entry.id,
                "parentId": entry.parent_id,
                "type": entry.type.value,
                "timestamp": entry.timestamp,
                "payload": entry.payload,
            }
        )
        with tome_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _load_tome_headers(self) -> None:
        if not self._tome_dir.exists():
            return
        for f in self._tome_dir.glob("*.jsonl"):
            try:
                meta = self._load_tome_metadata(f.stem)
                if meta:
                    self._tomles[meta.id] = meta
            except json.JSONDecodeError, ValueError:
                continue

    def _load_tome_metadata(self, tome_id_or_path: str | Path) -> TomeMetadata | None:
        path = Path(tome_id_or_path)
        if path.is_file():
            tome_file = path
        else:
            tome_file = self._tome_file_path(str(tome_id_or_path))
        if not tome_file.exists():
            return None

        with tome_file.open("r", encoding="utf-8") as f:
            first_line = f.readline()
            if not first_line:
                return None
            header = json.loads(first_line)
            if header.get("type") != "session":
                return None
            return TomeMetadata(
                id=header["id"],
                created_at=header["timestamp"],
                cwd=header["cwd"],
                parent_tome_id=header.get("parentSession"),
                active_leaf_id=header.get("activeLeafId"),
                schema_version=header.get("schema_version", "1.0"),
            )

    def _read_tome_entries(self, tome_id: str) -> list[TomeEntry]:
        resolved_id = self._resolve_tome_id(tome_id) or tome_id
        if resolved_id in self._entries_cache:
            self._entries_cache.move_to_end(resolved_id)
            return self._entries_cache[resolved_id]
        entries = self._read_tome_entries_from_disk(resolved_id)
        self._entries_cache[resolved_id] = entries
        self._entries_cache.move_to_end(resolved_id)
        while len(self._entries_cache) > self._MAX_CACHE_SIZE:
            self._entries_cache.popitem(last=False)
        return entries

    def _read_tome_entries_from_disk(self, tome_id: str) -> list[TomeEntry]:
        tome_file = self._tome_file_path(tome_id)
        if not tome_file.exists():
            return []
        with tome_file.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if not lines:
            return []
        entries: list[TomeEntry] = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            entry = TomeEntry(
                id=raw["id"],
                parent_id=raw.get("parentId"),
                type=TomeEntryType(raw["type"]),
                timestamp=raw["timestamp"],
                payload=raw.get("payload", {}),
            )
            entries.append(entry)
        return entries

    def _write_tome_file(
        self, metadata: TomeMetadata, entries: list[TomeEntry]
    ) -> None:
        tome_file = self._tome_file_path(metadata.id)
        header = {
            "type": "session",
            "version": 3,
            "id": metadata.id,
            "timestamp": metadata.created_at,
            "cwd": metadata.cwd,
            "schema_version": metadata.schema_version,
        }
        if metadata.parent_tome_id:
            header["parentSession"] = metadata.parent_tome_id
        if metadata.active_leaf_id:
            header["activeLeafId"] = metadata.active_leaf_id

        with tome_file.open("w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            for entry in entries:
                line = json.dumps(
                    {
                        "id": entry.id,
                        "parentId": entry.parent_id,
                        "type": entry.type.value,
                        "timestamp": entry.timestamp,
                        "payload": entry.payload,
                    }
                )
                f.write(line + "\n")

    def _filter_entries_to_leaf(
        self, entries: list[TomeEntry], leaf_id: str
    ) -> list[TomeEntry]:
        entry_by_id = {e.id: e for e in entries}
        path: list[TomeEntry] = []
        current_id: str | None = leaf_id
        visited: set[str] = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            entry = entry_by_id.get(current_id)
            if not entry:
                break
            path.insert(0, entry)
            current_id = entry.parent_id
        return path
