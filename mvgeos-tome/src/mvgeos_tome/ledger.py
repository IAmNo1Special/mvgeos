from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mvgeos_tome.locking import FileLock
from mvgeos_tome.types import (
    TomeEntry,
    TomeEntryType,
    TomeIntegrityIssue,
    TomeIntegrityReport,
    TomeMetadata,
)

logger = logging.getLogger(__name__)


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
                except json.JSONDecodeError, KeyError, ValueError:
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
            except json.JSONDecodeError, KeyError, ValueError:
                continue

    def _load_tome_metadata(self, tome_id_or_path: str | Path) -> TomeMetadata | None:
        path = Path(tome_id_or_path)
        if path.is_file():
            tome_file = path
        else:
            tome_file = self._tome_file_path(str(tome_id_or_path))
        if not tome_file.exists():
            return None

        try:
            with tome_file.open("r", encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line:
                    return None
                header = json.loads(first_line)
                if not isinstance(header, dict) or header.get("type") != "session":
                    return None
                return TomeMetadata(
                    id=header["id"],
                    created_at=header["timestamp"],
                    cwd=header["cwd"],
                    parent_tome_id=header.get("parentSession"),
                    active_leaf_id=header.get("activeLeafId"),
                    schema_version=header.get("schema_version", "1.0"),
                )
        except json.JSONDecodeError, KeyError, ValueError:
            return None

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
        try:
            with tome_file.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logger.warning("Failed to read tome file %s: %s", tome_file, e)
            return []
        if not lines:
            return []
        entries: list[TomeEntry] = []
        for idx, raw_line in enumerate(lines[1:], start=2):
            line = raw_line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    logger.warning(
                        "Malformed entry in tome %s at line %d: expected JSON object",
                        tome_id,
                        idx,
                    )
                    continue
                entry = TomeEntry(
                    id=raw["id"],
                    parent_id=raw.get("parentId"),
                    type=TomeEntryType(raw["type"]),
                    timestamp=float(raw["timestamp"]),
                    payload=raw.get("payload", {}),
                )
                entries.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                logger.warning(
                    "Damaged entry in tome %s at line %d: %s",
                    tome_id,
                    idx,
                    e,
                )
                continue
        return entries

    def verify_integrity(self, tome_id: str | Path) -> TomeIntegrityReport:
        with self._lock:
            if isinstance(tome_id, Path):
                target_path = tome_id
                resolved_id = target_path.stem
            elif Path(tome_id).is_file():
                target_path = Path(tome_id)
                resolved_id = target_path.stem
            else:
                resolved_id = self._resolve_tome_id(str(tome_id)) or str(tome_id)
                target_path = self._tome_file_path(resolved_id)

            if not target_path.exists():
                return TomeIntegrityReport(
                    valid=False,
                    tome_id=resolved_id,
                    issues=[
                        TomeIntegrityIssue(
                            line_number=0,
                            message=f"Tome file does not exist: {target_path}",
                        )
                    ],
                    total_lines=0,
                    valid_entries_count=0,
                )

            try:
                with target_path.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as e:
                return TomeIntegrityReport(
                    valid=False,
                    tome_id=resolved_id,
                    issues=[
                        TomeIntegrityIssue(
                            line_number=0,
                            message=f"Failed to read file: {e}",
                        )
                    ],
                    total_lines=0,
                    valid_entries_count=0,
                )

            if not lines:
                return TomeIntegrityReport(
                    valid=False,
                    tome_id=resolved_id,
                    issues=[
                        TomeIntegrityIssue(
                            line_number=1,
                            message="Tome file is empty (missing session header)",
                        )
                    ],
                    total_lines=0,
                    valid_entries_count=0,
                )

            issues: list[TomeIntegrityIssue] = []
            total_lines = len(lines)
            valid_entries_count = 0

            # Line 1: Header verification
            header_raw = lines[0].rstrip("\r\n")
            if not header_raw.strip():
                issues.append(
                    TomeIntegrityIssue(
                        line_number=1,
                        message="Missing session header (line is empty)",
                        raw_line=header_raw,
                    )
                )
            else:
                try:
                    header = json.loads(header_raw)
                    if not isinstance(header, dict):
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=1,
                                message="Invalid session header: expected JSON object",
                                raw_line=header_raw,
                            )
                        )
                    else:
                        if header.get("type") != "session":
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=1,
                                    message=(
                                        "Invalid session header: missing or "
                                        f"invalid 'type' (expected 'session', "
                                        f"got {header.get('type')!r})"
                                    ),
                                    raw_line=header_raw,
                                )
                            )
                        if not header.get("id") or not isinstance(
                            header.get("id"), str
                        ):
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=1,
                                    message=(
                                        "Invalid session header: "
                                        "missing or invalid 'id'"
                                    ),
                                    raw_line=header_raw,
                                )
                            )
                        elif header.get("id") != target_path.stem:
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=1,
                                    message=(
                                        "Header ID mismatch: expected "
                                        f"'{target_path.stem}', "
                                        f"got '{header.get('id')}'"
                                    ),
                                    raw_line=header_raw,
                                )
                            )

                        if "cwd" not in header or not isinstance(
                            header.get("cwd"), str
                        ):
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=1,
                                    message=(
                                        "Invalid session header: "
                                        "missing or invalid 'cwd'"
                                    ),
                                    raw_line=header_raw,
                                )
                            )
                        if "timestamp" not in header or not isinstance(
                            header.get("timestamp"), str
                        ):
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=1,
                                    message=(
                                        "Invalid session header: "
                                        "missing or invalid 'timestamp'"
                                    ),
                                    raw_line=header_raw,
                                )
                            )
                except json.JSONDecodeError as e:
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=1,
                            message=f"Corrupted session header: invalid JSON: {e}",
                            raw_line=header_raw,
                        )
                    )

            # Lines 2+: Entries verification
            for idx, raw in enumerate(lines[1:], start=2):
                line = raw.rstrip("\r\n")
                if not line.strip():
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message="Empty or blank line in JSONL stream",
                            raw_line=line,
                        )
                    )
                    continue

                try:
                    entry_raw = json.loads(line)
                except json.JSONDecodeError as e:
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message=f"Invalid JSON (truncated or corrupted): {e}",
                            raw_line=line,
                        )
                    )
                    continue

                if not isinstance(entry_raw, dict):
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message="Malformed entry: expected JSON object",
                            raw_line=line,
                        )
                    )
                    continue

                has_entry_issue = False
                if not entry_raw.get("id") or not isinstance(entry_raw.get("id"), str):
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message="Malformed entry: missing or invalid 'id' field",
                            raw_line=line,
                        )
                    )
                    has_entry_issue = True

                entry_type_raw = entry_raw.get("type")
                if not entry_type_raw or not isinstance(entry_type_raw, str):
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message="Malformed entry: missing or invalid 'type' field",
                            raw_line=line,
                        )
                    )
                    has_entry_issue = True
                else:
                    try:
                        TomeEntryType(entry_type_raw)
                    except ValueError:
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=idx,
                                message=(
                                    f"Malformed entry: invalid entry type "
                                    f"'{entry_type_raw}'"
                                ),
                                raw_line=line,
                            )
                        )
                        has_entry_issue = True

                ts = entry_raw.get("timestamp")
                if (
                    ts is None
                    or isinstance(ts, bool)
                    or not isinstance(ts, (int, float))
                ):
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message=(
                                "Malformed entry: missing or invalid 'timestamp' "
                                "(must be number)"
                            ),
                            raw_line=line,
                        )
                    )
                    has_entry_issue = True

                payload = entry_raw.get("payload")
                if payload is not None and not isinstance(payload, dict):
                    issues.append(
                        TomeIntegrityIssue(
                            line_number=idx,
                            message="Malformed entry: 'payload' must be an object/dict",
                            raw_line=line,
                        )
                    )
                    has_entry_issue = True

                if not has_entry_issue:
                    valid_entries_count += 1

            return TomeIntegrityReport(
                valid=len(issues) == 0,
                tome_id=resolved_id,
                issues=issues,
                total_lines=total_lines,
                valid_entries_count=valid_entries_count,
            )

    async def verify_integrity_async(self, tome_id: str | Path) -> TomeIntegrityReport:
        return await asyncio.to_thread(self.verify_integrity, tome_id)

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

    async def append_async(self, tome_id: str, entry: TomeEntry) -> None:
        await asyncio.to_thread(self.append, tome_id, entry)

    async def append_message_async(
        self,
        tome_id: str,
        role: str,
        content: Any,
        parent_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> TomeEntry:
        return await asyncio.to_thread(
            self.append_message,
            tome_id,
            role,
            content,
            parent_id,
            model,
            provider,
        )

    async def append_leaf_async(self, tome_id: str, target_id: str) -> TomeEntry:
        return await asyncio.to_thread(self.append_leaf, tome_id, target_id)

    async def append_custom_async(
        self,
        tome_id: str,
        payload: dict[str, Any],
        parent_id: str | None = None,
    ) -> TomeEntry:
        return await asyncio.to_thread(self.append_custom, tome_id, payload, parent_id)

    async def append_compaction_async(
        self,
        tome_id: str,
        payload: dict[str, Any],
        parent_id: str | None = None,
    ) -> TomeEntry:
        return await asyncio.to_thread(
            self.append_compaction, tome_id, payload, parent_id
        )

    async def append_label_async(
        self, tome_id: str, label: str, parent_id: str | None = None
    ) -> TomeEntry:
        return await asyncio.to_thread(self.append_label, tome_id, label, parent_id)

    async def append_tome_info_async(
        self, tome_id: str, payload: dict[str, Any]
    ) -> TomeEntry:
        return await asyncio.to_thread(self.append_tome_info, tome_id, payload)

    async def create_tome_async(
        self,
        metadata_or_cwd: TomeMetadata | str,
        parent_tome_id: str | None = None,
        tome_id: str | None = None,
    ) -> TomeMetadata:
        return await asyncio.to_thread(
            self.create_tome, metadata_or_cwd, parent_tome_id, tome_id
        )

    async def create_branched_tome_async(
        self,
        parent_tome_id: str,
        cwd: str,
        fork_from_leaf_id: str | None = None,
        tome_id: str | None = None,
    ) -> TomeMetadata:
        return await asyncio.to_thread(
            self.create_branched_tome,
            parent_tome_id,
            cwd,
            fork_from_leaf_id,
            tome_id,
        )

    async def get_entries_async(
        self,
        tome_id: str,
        entry_type: TomeEntryType | None = None,
        limit: int | None = None,
    ) -> list[TomeEntry]:
        return await asyncio.to_thread(self.get_entries, tome_id, entry_type, limit)

    async def get_entry_async(self, tome_id: str, entry_id: str) -> TomeEntry | None:
        return await asyncio.to_thread(self.get_entry, tome_id, entry_id)

    async def get_leaf_id_async(self, tome_id: str) -> str | None:
        return await asyncio.to_thread(self.get_leaf_id, tome_id)

    async def get_entries_for_context_async(
        self,
        tome_id: str,
        leaf_id: str | None = None,
        max_entries: int | None = None,
    ) -> list[TomeEntry]:
        return await asyncio.to_thread(
            self.get_entries_for_context, tome_id, leaf_id, max_entries
        )

    async def open_tome_async(self, tome_id: str) -> TomeMetadata | None:
        return await asyncio.to_thread(self.open_tome, tome_id)

    async def open_recent_async(self, cwd: str) -> TomeMetadata | None:
        return await asyncio.to_thread(self.open_recent, cwd)
