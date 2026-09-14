from __future__ import annotations

import json
import os
import threading
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import portalocker

from mvgeos_tome.types import (
    CURRENT_SESSION_VERSION,
    TomeEntry,
    TomeEntryType,
    TomeMetadata,
    TomeVersionError,
)


@dataclass(frozen=True, slots=True)
class Revision:
    """Single invalidation token: filesystem identity + size + mtime_ns."""

    mtime_ns: int
    size: int
    ino: int

    @staticmethod
    def from_path(path: Path) -> Revision | None:
        try:
            st = path.stat()
            return Revision(st.st_mtime_ns, st.st_size, st.st_ino)
        except FileNotFoundError:
            return None


def _parse_tome_entry(raw: dict[str, Any]) -> TomeEntry:
    return TomeEntry(
        id=raw["id"],
        parent_id=raw.get("parentId"),
        type=TomeEntryType(raw["type"]),
        timestamp=float(raw["timestamp"]),
        payload=raw.get("payload", {}),
    )


def _filter_entries_to_leaf(entries: list[TomeEntry], leaf_id: str) -> list[TomeEntry]:
    """Filter entries to only include the branch ending at leaf_id."""
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


class TomeHandle:
    """A handle to a single tome; read handles share, write is exclusive."""

    def __init__(self, tome_dir: Path, tome_id: str, mode: str) -> None:
        self._tome_dir = Path(tome_dir).expanduser().resolve()
        self._tome_id = tome_id
        self._mode = mode  # "r" or "w"
        self._path = self._tome_dir / f"{tome_id}.jsonl"
        self._revision: Revision | None = None
        self._entries_cache: list[TomeEntry] = []
        self._header: dict[str, Any] | None = None
        self._lease: portalocker.Lock | None = None
        self._local_lock = threading.RLock()

    @property
    def tome_id(self) -> str:
        return self._tome_id

    @property
    def path(self) -> Path:
        return self._path

    @property
    def mode(self) -> str:
        return self._mode

    @contextmanager
    def _acquire(self) -> Generator[None]:
        """Acquire kernel lease for write mode. Read mode: no lease, just stat."""
        if self._mode == "w":
            self._lease = portalocker.Lock(
                str(self._path) + ".lock",
                timeout=30,
                flags=portalocker.LOCK_EX,
            )
            self._lease.acquire()
            self._revision = Revision.from_path(self._path)
        try:
            yield
        finally:
            if self._lease:
                self._lease.release()
                self._lease = None

    # ── Read API (both modes) ──────────────────────────────────

    def _load_snapshot(self) -> list[TomeEntry]:
        """Load the full file into memory (Pi-style mirror)."""
        if not self._path.exists():
            self._entries_cache = []
            self._header = None
            self._revision = None
            return []
        with self._path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if not lines:
            self._entries_cache = []
            self._header = None
            self._revision = Revision.from_path(self._path)
            return []
        try:
            header = json.loads(lines[0])
        except json.JSONDecodeError:
            self._entries_cache = []
            self._header = None
            self._revision = Revision.from_path(self._path)
            return []
        if not isinstance(header, dict) or header.get("type") != "session":
            self._entries_cache = []
            self._header = None
            self._revision = Revision.from_path(self._path)
            return []
        version_raw = header.get("version", 1)
        try:
            version = int(version_raw)
        except (ValueError, TypeError):
            raise TomeVersionError(
                version_raw, f"Invalid session version: {version_raw}"
            ) from None
        if version != 1:
            raise TomeVersionError(version, f"Unsupported session version: {version}")
        self._header = header
        entries = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    continue
                if not raw.get("type") or "id" not in raw or "timestamp" not in raw:
                    continue
                entries.append(_parse_tome_entry(raw))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue
        self._entries_cache = entries
        self._revision = Revision.from_path(self._path)
        return entries

    def get_entries(self) -> list[TomeEntry]:
        """Snapshot read - mirror IS the cache. No separate validation."""
        with self._local_lock:
            rev = Revision.from_path(self._path)
            if self._entries_cache and self._revision == rev:
                return self._entries_cache
            return self._load_snapshot()

    def get_metadata(self) -> TomeMetadata | None:
        """Return parsed header metadata."""
        with self._local_lock:
            rev = Revision.from_path(self._path)
            if self._header is not None and self._revision == rev:
                return self._header_to_metadata(self._header)
            self._load_snapshot()
            if self._header is not None:
                return self._header_to_metadata(self._header)
            return None

    def _header_to_metadata(self, header: dict[str, Any]) -> TomeMetadata:
        return TomeMetadata(
            id=header["id"],
            created_at=header["timestamp"],
            cwd=header["cwd"],
            parent_tome_id=header.get("parentSession"),
            active_leaf_id=header.get("activeLeafId"),
            schema_version=header.get("schema_version", "1.0"),
            version=header.get("version", 1),
            model=header.get("model"),
            contemplation_level=header.get("contemplationLevel"),
            spells=list(header.get("spells", []) or []),
        )

    def iter_entries(self) -> Generator[TomeEntry]:
        """Snapshot iteration - materialize once, yield without locks."""
        entries = self.get_entries()
        yield from entries

    def get_revision(self) -> Revision | None:
        """Single invalidation token - query cache keys on this."""
        return self._revision or Revision.from_path(self._path)

    # ── Write API (write mode only) ────────────────────────────

    def append(self, entry: TomeEntry) -> None:
        """Append single entry + durability barrier."""
        if self._mode != "w":
            raise RuntimeError("Read handle cannot append")
        with self._acquire():
            self._load_snapshot()
            self._entries_cache.append(entry)
            self._flush_to_disk()

    def replace(self, header: dict[str, Any], entries: list[TomeEntry]) -> None:
        """Atomic full rewrite (compaction/fork). tmp+rename+fsync."""
        if self._mode != "w":
            raise RuntimeError("Read handle cannot replace")
        with self._acquire():
            tmp = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
            try:
                with tmp.open("w", encoding="utf-8") as f:
                    f.write(json.dumps(header) + "\n")
                    for e in entries:
                        f.write(json.dumps(e.to_dict()) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self._path)
                # fsync directory for create visibility (Unix only;
                # Windows cannot open a directory handle).
                try:
                    with open(self._tome_dir) as dfd:
                        os.fsync(dfd.fileno())
                except (PermissionError, OSError):
                    pass  # Windows does not support directory fsync
                self._entries_cache = entries
                self._header = header
                self._revision = Revision.from_path(self._path)
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)

    def _flush_to_disk(self) -> None:
        """Durability barrier: append line + fsync file + fsync dir."""
        line = json.dumps(self._entries_cache[-1].to_dict()) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        # fsync directory for create visibility (Unix only;
        # Windows cannot open a directory handle).
        try:
            with open(self._tome_dir) as dfd:
                os.fsync(dfd.fileno())
        except (PermissionError, OSError):
            pass  # Windows does not support directory fsync
        self._revision = Revision.from_path(self._path)

    # ── Repair (resumer calls, not store) ──────────────────────

    def repair_torn_tail(self) -> int:
        """Truncate partial last line. Returns bytes truncated."""
        if self._mode != "w":
            raise RuntimeError("Read handle cannot repair")
        with self._acquire():
            if not self._path.exists():
                return 0
            with self._path.open("r+", encoding="utf-8") as f:
                content = f.read()
                if not content:
                    return 0
                lines = content.splitlines(keepends=True)
                last_complete = 0
                for i in range(len(lines) - 1, -1, -1):
                    try:
                        json.loads(lines[i])
                        last_complete = i + 1
                        break
                    except json.JSONDecodeError:
                        continue
                if last_complete < len(lines):
                    truncated = sum(len(ln.encode()) for ln in lines[last_complete:])
                    f.seek(0)
                    f.writelines(lines[:last_complete])
                    f.truncate()
                    f.flush()
                    os.fsync(f.fileno())
                    # Invalidate cache so the next read reloads the
                    # now-truncated file.
                    self._revision = None
                    self._entries_cache = []
                    return truncated
                return 0


def _generate_short_id() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _generate_id() -> str:
    import uuid

    return uuid.uuid4().hex


def _timestamp_now() -> float:
    from datetime import UTC, datetime

    return datetime.now(UTC).timestamp()


def _timestamp_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class TomeHandleFactory:
    """Factory for creating tome handles with write-leaf-entry helper."""

    def __init__(self, tome_dir: Path) -> None:
        self._tome_dir = Path(tome_dir).expanduser().resolve()

    def _resolve_tome_id(self, tome_id: str) -> str | None:
        """Resolve short ID prefix to full tome ID."""
        if not tome_id:
            return None
        if not self._tome_dir.exists():
            return None
        stems = [f.stem for f in self._tome_dir.glob("*.jsonl") if f.is_file()]
        exact = [s for s in stems if s == tome_id]
        if len(exact) == 1:
            return exact[0]
        case_matches = [s for s in stems if s.lower() == tome_id.lower()]
        if len(case_matches) == 1:
            return case_matches[0]
        prefix_matches = [s for s in stems if s.lower().startswith(tome_id.lower())]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        return None

    def _validate_tome_file(self, path: Path) -> tuple[bool, dict[str, Any] | None]:
        """Validate tome file header. Returns (is_valid, header_dict)."""
        if not path.exists():
            return False, None
        try:
            with path.open("r", encoding="utf-8") as f:
                first = f.readline()
            if not first:
                return False, None
            header = json.loads(first)
            if not isinstance(header, dict) or header.get("type") != "session":
                return False, None
            version_raw = header.get("version", 1)
            try:
                version = int(version_raw)
            except (ValueError, TypeError):
                return False, None
            if version != 1:
                return False, None
            return True, header
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return False, None

    def create_tome(
        self,
        cwd: str,
        *,
        tome_id: str | None = None,
        model: str | None = None,
        contemplation_level: str | None = None,
        spells: Sequence[str] | None = None,
    ) -> TomeHandle:
        """Create a new tome and return a write handle."""
        from mvgeos_tome.types import CURRENT_SESSION_VERSION

        tid = tome_id or _generate_id()
        header = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": tid,
            "timestamp": _timestamp_iso(),
            "cwd": cwd,
            "schema_version": "1.0",
        }
        if model is not None:
            header["model"] = model
        if contemplation_level is not None:
            header["contemplationLevel"] = contemplation_level
        if spells:
            header["spells"] = spells

        write_handle = TomeHandle(self._tome_dir, tid, "w")
        write_handle.replace(header, [])
        return write_handle

    def create_branched_tome(
        self,
        parent_tome_id: str,
        cwd: str,
        fork_from_leaf_id: str | None = None,
        *,
        tome_id: str | None = None,
        model: str | None = None,
        contemplation_level: str | None = None,
        spells: list[str] | None = None,
    ) -> TomeHandle:
        """Create a new tome branched from an existing tome at a specific leaf."""
        resolved_parent = self._resolve_tome_id(parent_tome_id)
        if resolved_parent is None:
            raise ValueError(f"Parent tome not found: {parent_tome_id}")

        parent_read_handle = self.open_read(resolved_parent)
        parent_meta = parent_read_handle.get_metadata()
        if parent_meta is None:
            raise ValueError(f"Parent tome metadata not found: {parent_tome_id}")

        parent_entries = parent_read_handle.get_entries()

        # Filter entries to the fork point
        if fork_from_leaf_id:
            entries = _filter_entries_to_leaf(parent_entries, fork_from_leaf_id)
        else:
            entries = parent_entries

        tid = tome_id or _generate_id()
        header = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": tid,
            "timestamp": _timestamp_iso(),
            "cwd": cwd,
            "schema_version": "1.0",
            "parentSession": parent_meta.id,
            "activeLeafId": fork_from_leaf_id or parent_meta.active_leaf_id,
        }
        if model is not None:
            header["model"] = model
        elif parent_meta.model:
            header["model"] = parent_meta.model
        if contemplation_level is not None:
            header["contemplationLevel"] = contemplation_level
        elif parent_meta.contemplation_level:
            header["contemplationLevel"] = parent_meta.contemplation_level
        if spells is not None:
            header["spells"] = spells
        elif parent_meta.spells:
            header["spells"] = parent_meta.spells

        write_handle = TomeHandle(self._tome_dir, tid, "w")
        write_handle.replace(header, entries)
        return write_handle

    def open_read(self, tome_id: str) -> TomeHandle:
        """Open a read handle.

        Supports short ID prefix and case-insensitive matching. Raises
        TomeVersionError if the tome has an unsupported version.
        """
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None:
            # Return handle anyway - it will raise on get_entries.
            return TomeHandle(self._tome_dir, tome_id, "r")
        # Validate version upfront.
        path = self._tome_dir / f"{resolved}.jsonl"
        is_valid, _ = self._validate_tome_file(path)
        if not is_valid:
            try:
                with path.open("r", encoding="utf-8") as f:
                    first = f.readline()
                if first:
                    header = json.loads(first)
                    version_raw = header.get("version", 1)
                    try:
                        version = int(version_raw)
                        if version != 1:
                            raise TomeVersionError(
                                version,
                                f"Unsupported session version: {version}",
                            ) from None
                    except (ValueError, TypeError):
                        raise TomeVersionError(
                            version_raw,
                            f"Invalid session version: {version_raw}",
                        ) from None
            except TomeVersionError:
                raise
            except Exception:
                pass
        return TomeHandle(self._tome_dir, resolved, "r")

    def open_write(self, tome_id: str) -> TomeHandle:
        """Open a write handle. Creates tome if it doesn't exist."""
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None:
            # Create new tome with default config.
            write_handle = TomeHandle(self._tome_dir, tome_id, "w")
            header = {
                "type": "session",
                "version": 1,
                "id": tome_id,
                "timestamp": _timestamp_iso(),
                "cwd": str(self._tome_dir),
                "schema_version": "1.0",
            }
            write_handle.replace(header, [])
            return write_handle
        return TomeHandle(self._tome_dir, resolved, "w")

    def list_tomes(self) -> list[str]:
        if not self._tome_dir.exists():
            return []
        valid_tomes = []
        for f in self._tome_dir.glob("*.jsonl"):
            if f.is_file():
                is_valid, _ = self._validate_tome_file(f)
                if is_valid:
                    valid_tomes.append(f.stem)
        return valid_tomes

    def verify_integrity(self, tome_id: str) -> dict[str, Any]:
        """Verify integrity of a tome file (bypasses cache)."""
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None:
            return {
                "valid": False,
                "tome_id": tome_id,
                "issues": [{"line_number": 0, "message": f"Tome not found: {tome_id}"}],
                "total_lines": 0,
                "valid_entries_count": 0,
            }
        path = self._tome_dir / f"{resolved}.jsonl"
        if not path.exists():
            return {
                "valid": False,
                "tome_id": resolved,
                "issues": [
                    {"line_number": 0, "message": f"Tome file not found: {path}"}
                ],
                "total_lines": 0,
                "valid_entries_count": 0,
            }

        issues: list[dict[str, Any]] = []
        total_lines = 0
        valid_entries_count = 0

        def _add(ln: int, message: str) -> None:
            issues.append({"line_number": ln, "message": message})

        try:
            with path.open("r", encoding="utf-8") as f:
                first = f.readline()
                total_lines += 1
                if not first:
                    _add(1, "Tome file is empty (missing session header)")
                else:
                    try:
                        header = json.loads(first)
                        if not isinstance(header, dict):
                            _add(1, "Invalid session header: expected JSON object")
                        else:
                            if header.get("type") != "session":
                                _add(
                                    1,
                                    (
                                        "Invalid session header: missing or "
                                        "invalid 'type' "
                                        f"(expected 'session', "
                                        f"got {header.get('type')!r})"
                                    ),
                                )
                            if not header.get("id") or not isinstance(
                                header.get("id"), str
                            ):
                                _add(
                                    1,
                                    "Invalid session header: missing or invalid 'id'",
                                )
                            elif header.get("id") != resolved:
                                _add(
                                    1,
                                    (
                                        "Header ID mismatch: "
                                        f"expected '{resolved}', "
                                        f"got '{header.get('id')}'"
                                    ),
                                )
                            if "cwd" not in header or not isinstance(
                                header.get("cwd"), str
                            ):
                                _add(
                                    1,
                                    "Invalid session header: missing or invalid 'cwd'",
                                )
                            if "timestamp" not in header or not isinstance(
                                header.get("timestamp"), str
                            ):
                                _add(
                                    1,
                                    "Invalid session header: missing or invalid "
                                    "'timestamp'",
                                )
                            version_raw = header.get("version", 1)
                            try:
                                version = int(version_raw)
                                if version != 1:
                                    _add(
                                        1,
                                        f"Unsupported session version: {version}",
                                    )
                            except (ValueError, TypeError):
                                _add(
                                    1,
                                    f"Invalid session version: {version_raw}",
                                )
                    except json.JSONDecodeError as e:
                        _add(1, f"Corrupted session header: invalid JSON: {e}")

                # Lines 2+: Entries verification
                for idx, raw in enumerate(f, start=2):
                    total_lines += 1
                    line = raw.rstrip("\r\n")
                    if not line.strip():
                        _add(idx, "Empty or blank line in JSONL stream")
                        continue

                    try:
                        entry_raw = json.loads(line)
                    except json.JSONDecodeError as e:
                        _add(idx, f"Invalid JSON (truncated or corrupted): {e}")
                        continue

                    if not isinstance(entry_raw, dict):
                        _add(idx, "Malformed entry: expected JSON object")
                        continue

                    has_entry_issue = False
                    if not entry_raw.get("id") or not isinstance(
                        entry_raw.get("id"), str
                    ):
                        _add(
                            idx,
                            "Malformed entry: missing or invalid 'id' field",
                        )
                        has_entry_issue = True

                    entry_type_raw = entry_raw.get("type")
                    if not entry_type_raw or not isinstance(entry_type_raw, str):
                        _add(
                            idx,
                            "Malformed entry: missing or invalid 'type' field",
                        )
                        has_entry_issue = True
                    else:
                        try:
                            TomeEntryType(entry_type_raw)
                        except ValueError:
                            _add(
                                idx,
                                (
                                    "Malformed entry: invalid entry type "
                                    f"'{entry_type_raw}'"
                                ),
                            )
                            has_entry_issue = True

                    ts = entry_raw.get("timestamp")
                    if (
                        ts is None
                        or isinstance(ts, bool)
                        or not isinstance(ts, (int, float))
                    ):
                        _add(
                            idx,
                            "Malformed entry: missing or invalid 'timestamp' "
                            "(must be number)",
                        )
                        has_entry_issue = True

                    payload = entry_raw.get("payload")
                    if payload is not None and not isinstance(payload, dict):
                        _add(
                            idx,
                            "Malformed entry: 'payload' must be an object/dict",
                        )
                        has_entry_issue = True

                    if not has_entry_issue:
                        valid_entries_count += 1

            return {
                "valid": len(issues) == 0,
                "tome_id": resolved,
                "issues": issues,
                "total_lines": total_lines,
                "valid_entries_count": valid_entries_count,
            }
        except Exception as e:
            return {
                "valid": False,
                "tome_id": resolved,
                "issues": [{"line_number": 0, "message": f"Failed to read file: {e}"}],
                "total_lines": 0,
                "valid_entries_count": 0,
            }
