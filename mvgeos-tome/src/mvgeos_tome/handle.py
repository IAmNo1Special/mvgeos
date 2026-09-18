from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker

from mvgeos_tome.types import (
    CURRENT_SESSION_VERSION,
    ATIFMetrics,
    ATIFTrajectory,
    ATIFTrajectoryStep,
    TomeEntry,
    TomeEntryType,
    TomeIntegrityIssue,
    TomeIntegrityReport,
    TomeMetadata,
    TomeVersionError,
)

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class Revision:
    """Single invalidation token: filesystem identity + size + mtime."""

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


def _generate_short_id() -> str:
    return uuid.uuid4().hex[:8]


def _generate_id() -> str:
    return uuid.uuid4().hex


_TOME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _validate_tome_id(tome_id: str) -> str:
    """Allowlist a tome id before it touches the filesystem.

    Tome ids become `{id}.jsonl` file names; anything outside the allowlist
    (path separators, `..`, absolute paths, empty strings) is rejected so a
    caller-supplied id can never escape the tome directory.
    """
    if not _TOME_ID_RE.match(tome_id):
        raise ValueError(f"Invalid tome id: {tome_id!r}")
    return tome_id


def _timestamp_now() -> float:
    return datetime.now(UTC).timestamp()


def _timestamp_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def _fsync_dir(dir_path: Path) -> None:
    """Fsync a directory so file creates/renames survive a crash.

    No-op on Windows, which cannot open a directory handle.
    """
    if os.name == "nt":
        return
    fd = os.open(dir_path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class TomeHandle:
    """A handle to a single tome; read handles share, write is exclusive.

    The on-disk JSONL file is the source of truth. Each handle keeps an
    in-memory mirror that is revalidated against a filesystem revision token
    on every read, so any number of handles across threads and processes stay
    coherent without shared caches.
    """

    def __init__(self, tome_dir: Path, tome_id: str, mode: str) -> None:
        self._tome_dir = Path(tome_dir).expanduser().resolve()
        self._tome_id = _validate_tome_id(tome_id)
        self._mode = mode  # "r" or "w"
        self._path = self._tome_dir / f"{self._tome_id}.jsonl"
        self._revision: Revision | None = None
        self._entries_cache: list[TomeEntry] | None = None
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
    def locked(self) -> Generator[None]:
        """Hold this handle's local mutex across a compound operation.

        Reentrant: may be held while calling append/append_leaf/replace.
        Note: this guards threads in this process only. Each mutating call
        still acquires and releases the kernel lease independently, so two
        processes can interleave their compound operations; keep multi-step
        mutations to a single writer process per tome.
        """
        with self._local_lock:
            yield

    @contextmanager
    def _acquire(self) -> Generator[None]:
        """Acquire the local mutex plus the kernel lease for write mode.

        Lock order is always local-then-lease. Read mode takes no lease:
        reads are stat-validated snapshots.
        """
        with self._local_lock:
            if self._mode == "w":
                self._lease = portalocker.Lock(
                    str(self._path) + ".lock",
                    timeout=_LOCK_TIMEOUT,
                )
                self._lease.acquire()
                self._revision = Revision.from_path(self._path)
            try:
                yield
            finally:
                if self._lease is not None:
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
            header = json.loads(lines[0].strip())
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
        version_raw = header.get("version", CURRENT_SESSION_VERSION)
        try:
            version = int(version_raw)
        except (ValueError, TypeError) as e:
            raise TomeVersionError(
                version_raw, f"Invalid session version: {version_raw}"
            ) from e
        if version != CURRENT_SESSION_VERSION:
            raise TomeVersionError(version, f"Unsupported session version: {version}")
        self._header = header
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
                        self._tome_id,
                        idx,
                    )
                    continue
                entries.append(_parse_tome_entry(raw))
            except (
                json.JSONDecodeError,
                KeyError,
                ValueError,
                TypeError,
            ) as e:
                logger.warning(
                    "Damaged entry in tome %s at line %d: %s",
                    self._tome_id,
                    idx,
                    e,
                )
                continue
        self._entries_cache = entries
        self._revision = Revision.from_path(self._path)
        return entries

    def get_entries(self) -> list[TomeEntry]:
        """Snapshot read; the mirror is revalidated on every call."""
        with self._local_lock:
            rev = Revision.from_path(self._path)
            if self._entries_cache is not None and self._revision == rev:
                return list(self._entries_cache)
            return list(self._load_snapshot())

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
            version=header.get("version", CURRENT_SESSION_VERSION),
            model=header.get("model"),
            contemplation_level=header.get("contemplationLevel"),
            spells=list(header.get("spells", []) or []),
        )

    def iter_entries(self) -> Generator[TomeEntry]:
        """Snapshot iteration over a materialized copy; holds no locks."""
        yield from self.get_entries()

    def get_revision(self) -> Revision | None:
        """Single invalidation token for this tome's file."""
        return self._revision or Revision.from_path(self._path)

    # ── Write API (write mode only) ────────────────────────────

    def append(self, entry: TomeEntry) -> None:
        """Append a single entry plus a durability barrier."""
        if self._mode != "w":
            raise RuntimeError("Read handle cannot append")
        with self._acquire():
            self._load_snapshot()
            if self._entries_cache is None:
                raise RuntimeError("Failed to load tome snapshot before append")
            self._entries_cache.append(entry)
            self._flush_to_disk()

    def append_leaf(self, target_id: str) -> TomeEntry:
        """Point the Tome's Leaf at an entry, syncing header and entries.

        A single atomic step under the lease: appends the LEAF marker entry
        and records it as the header's activeLeafId, mirroring the previous
        whole-file rewrite cost without ever serving a split header/log.
        """
        if self._mode != "w":
            raise RuntimeError("Read handle cannot append")
        with self._acquire():
            self._load_snapshot()
            if self._entries_cache is None:
                raise RuntimeError("Failed to load tome snapshot before append_leaf")
            leaf = TomeEntry(
                id=_generate_short_id(),
                parent_id=None,
                type=TomeEntryType.LEAF,
                timestamp=_timestamp_now(),
                payload={"targetId": target_id},
            )
            entries = list(self._entries_cache)
            entries.append(leaf)
            header = dict(self._header or {})
            header["activeLeafId"] = target_id
            self._replace_locked(header, entries)
        return leaf

    def replace(self, header: dict[str, Any], entries: list[TomeEntry]) -> None:
        """Atomic full rewrite (compaction/fork) via tmp file + rename."""
        if self._mode != "w":
            raise RuntimeError("Read handle cannot replace")
        with self._acquire():
            self._replace_locked(header, entries)

    def _replace_locked(self, header: dict[str, Any], entries: list[TomeEntry]) -> None:
        """Rewrite the file; caller must hold the lease via _acquire()."""
        tmp = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                f.write(json.dumps(header) + "\n")
                for e in entries:
                    f.write(json.dumps(e.to_dict()) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
            _fsync_dir(self._tome_dir)
            self._entries_cache = list(entries)
            self._header = dict(header)
            self._revision = Revision.from_path(self._path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _flush_to_disk(self) -> None:
        """Durability barrier: append last entry, fsync file and directory."""
        if self._entries_cache is None:
            raise RuntimeError("No snapshot loaded; nothing to flush")
        line = json.dumps(self._entries_cache[-1].to_dict()) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        _fsync_dir(self._tome_dir)
        self._revision = Revision.from_path(self._path)

    # ── Repair (resumer calls, not readers) ────────────────────

    def repair_torn_tail(self) -> int:
        """Truncate a partial last line left by a crashed writer.

        Operates on raw bytes so platform newline translation can never
        corrupt the file. Only the tail is touched: middle lines (even
        damaged ones) are preserved for readers to skip and the auditor
        to flag. Returns the number of bytes truncated.
        """
        if self._mode != "w":
            raise RuntimeError("Read handle cannot repair")
        with self._acquire():
            if not self._path.exists():
                return 0
            with self._path.open("rb") as f:
                content = f.read()
            if not content:
                return 0
            lines = content.split(b"\n")
            last_complete = -1
            for i, raw in enumerate(lines):
                if i == len(lines) - 1 and raw == b"":
                    continue  # trailing newline, not a line
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue  # torn multi-byte sequence
                if not text.strip():
                    continue
                try:
                    json.loads(text)
                except json.JSONDecodeError:
                    continue
                last_complete = i
            if last_complete < 0:
                return 0  # nothing parseable: corruption, not a torn tail
            repaired = b"\n".join(lines[: last_complete + 1]) + b"\n"
            if repaired == content:
                return 0
            with self._path.open("r+b") as f:
                f.seek(0)
                f.write(repaired)
                f.truncate()
                f.flush()
                os.fsync(f.fileno())
            # Invalidate the mirror so the next read reloads.
            self._revision = None
            self._entries_cache = None
            self._header = None
            return len(content) - len(repaired)


class TomeHandleFactory:
    """Stateless entry point for tome persistence.

    Holds no caches: every query rescans the directory or revalidates the
    file revision, so any number of factories, handles, threads, and
    processes stay coherent. The JSONL file is the source of truth.
    """

    def __init__(self, tome_dir: Path) -> None:
        self._tome_dir = Path(tome_dir).expanduser().resolve()

    @property
    def dir(self) -> Path:
        return self._tome_dir

    def _resolve_tome_id(self, tome_id: str) -> str | None:
        """Resolve a full, case-insensitive, or prefix id to a full tome id."""
        if not tome_id:
            return None
        if not self._tome_dir.exists():
            return None
        stems = [f.stem for f in self._tome_dir.glob("*.jsonl") if f.is_file()]
        if tome_id in stems:
            return tome_id
        exact = [s for s in stems if s.lower() == tome_id.lower()]
        if len(exact) == 1:
            return exact[0]
        prefix = [s for s in stems if s.lower().startswith(tome_id.lower())]
        if len(prefix) == 1:
            return prefix[0]
        return None

    def _read_header(self, path: Path) -> dict[str, Any] | None:
        """Read and validate a session header; None when absent or corrupt."""
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                first = f.readline()
            if not first:
                return None
            header = json.loads(first)
            if not isinstance(header, dict) or header.get("type") != "session":
                return None
            version_raw = header.get("version", CURRENT_SESSION_VERSION)
            try:
                version = int(version_raw)
            except (ValueError, TypeError) as e:
                raise TomeVersionError(
                    version_raw, f"Invalid session version: {version_raw}"
                ) from e
            if version != CURRENT_SESSION_VERSION:
                raise TomeVersionError(
                    version, f"Unsupported session version: {version}"
                )
            return header
        except TomeVersionError:
            raise
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            return None

    def _header_to_metadata(self, header: dict[str, Any]) -> TomeMetadata:
        return TomeMetadata(
            id=header["id"],
            created_at=header["timestamp"],
            cwd=header["cwd"],
            parent_tome_id=header.get("parentSession"),
            active_leaf_id=header.get("activeLeafId"),
            schema_version=header.get("schema_version", "1.0"),
            version=header.get("version", CURRENT_SESSION_VERSION),
            model=header.get("model"),
            contemplation_level=header.get("contemplationLevel"),
            spells=list(header.get("spells", []) or []),
        )

    def _metadata_for(self, stem: str) -> TomeMetadata | None:
        try:
            header = self._read_header(self._tome_dir / f"{stem}.jsonl")
        except TomeVersionError:
            raise
        except OSError:
            return None
        if header is None:
            return None
        try:
            return self._header_to_metadata(header)
        except KeyError:
            return None

    def tome_file(self, tome_id: str) -> Path:
        """Resolve a tome id (or file path) to its JSONL file."""
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None:
            candidate = Path(tome_id)
            if candidate.is_file():
                resolved = self._resolve_tome_id(candidate.stem)
        return self._tome_dir / f"{resolved or _validate_tome_id(tome_id)}.jsonl"

    def list_tomes(self) -> list[TomeMetadata]:
        """Rescan the directory on every call; never serve a stale list."""
        if not self._tome_dir.exists():
            return []
        metas: list[TomeMetadata] = []
        for f in self._tome_dir.glob("*.jsonl"):
            if not f.is_file():
                continue
            try:
                meta = self._metadata_for(f.stem)
            except TomeVersionError as e:
                logger.warning("Failed to load header for %s: %s", f, e)
                continue
            if meta is not None:
                metas.append(meta)
        return metas

    def open_tome(self, tome_id: str) -> TomeMetadata | None:
        """Open tome metadata by id, prefix, or file path.

        Returns None when missing; raises TomeVersionError on bad versions.
        """
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None and Path(tome_id).is_file():
            resolved = self._resolve_tome_id(Path(tome_id).stem)
        if resolved is None:
            if not tome_id:
                return None
            return self._metadata_for(_validate_tome_id(tome_id))
        return self._metadata_for(resolved)

    def open_recent(self, cwd: str) -> TomeMetadata | None:
        """Most recently modified tome for a working directory."""
        if not self._tome_dir.exists():
            return None
        candidates = sorted(
            self._tome_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime_ns
        )
        for f in reversed(candidates):
            try:
                meta = self._metadata_for(f.stem)
            except TomeVersionError:
                continue
            if meta is not None and meta.cwd == cwd:
                return meta
        return None

    def create_tome(
        self,
        cwd: str,
        *,
        tome_id: str | None = None,
        model: str | None = None,
        contemplation_level: str | None = None,
        spells: Sequence[str] | None = None,
    ) -> TomeHandle:
        """Create a new tome and return a write handle.

        Raises ValueError when a tome with the requested id already exists.
        """
        self._tome_dir.mkdir(parents=True, exist_ok=True)
        tid = _validate_tome_id(tome_id) if tome_id else _generate_id()
        if (self._tome_dir / f"{tid}.jsonl").exists():
            raise ValueError(f"Tome already exists: {tid}")
        header: dict[str, Any] = {
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
            header["spells"] = list(spells)

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
        spells: Sequence[str] | None = None,
    ) -> TomeHandle:
        """Branch a tome by copying the ancestor chain up to a leaf entry."""
        resolved_parent = self._resolve_tome_id(parent_tome_id)
        if resolved_parent is None:
            raise ValueError(f"Parent tome not found: {parent_tome_id}")

        parent_read = self.open_read(resolved_parent)
        parent_meta = parent_read.get_metadata()
        if parent_meta is None:
            raise ValueError(f"Parent tome metadata not found: {parent_tome_id}")

        parent_entries = parent_read.get_entries()
        entries = (
            _filter_entries_to_leaf(parent_entries, fork_from_leaf_id)
            if fork_from_leaf_id
            else list(parent_entries)
        )

        tid = _validate_tome_id(tome_id) if tome_id else _generate_id()
        if (self._tome_dir / f"{tid}.jsonl").exists():
            raise ValueError(f"Tome already exists: {tid}")
        header: dict[str, Any] = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": tid,
            "timestamp": _timestamp_iso(),
            "cwd": cwd or parent_meta.cwd,
            "schema_version": "1.0",
            "parentSession": parent_meta.id,
            "activeLeafId": fork_from_leaf_id or parent_meta.active_leaf_id,
        }
        header["model"] = model if model is not None else parent_meta.model
        header["contemplationLevel"] = (
            contemplation_level
            if contemplation_level is not None
            else parent_meta.contemplation_level
        )
        header["spells"] = (
            list(spells) if spells is not None else list(parent_meta.spells)
        )

        write_handle = TomeHandle(self._tome_dir, tid, "w")
        write_handle.replace(header, entries)
        return write_handle

    def open_read(self, tome_id: str) -> TomeHandle:
        """Open a read handle; raises FileNotFoundError when unknown."""
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None and Path(tome_id).is_file():
            resolved = self._resolve_tome_id(Path(tome_id).stem)
        if resolved is None:
            raise FileNotFoundError(f"Tome not found: {tome_id}")
        handle = TomeHandle(self._tome_dir, resolved, "r")
        handle.get_metadata()
        return handle

    def open_write(self, tome_id: str) -> TomeHandle:
        """Open a write handle; raises FileNotFoundError when unknown.

        Tomes are only created via create_tome/create_branched_tome so the
        recorded cwd is always the project directory, never the tome dir.
        """
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None:
            raise FileNotFoundError(f"Tome not found: {tome_id}")
        handle = TomeHandle(self._tome_dir, resolved, "w")
        if handle.get_metadata() is None:
            raise ValueError(f"Tome has no readable header: {tome_id}")
        return handle

    def get_entries(
        self,
        tome_id: str,
        entry_type: TomeEntryType | None = None,
        limit: int | None = None,
    ) -> list[TomeEntry]:
        entries = self.open_read(tome_id).get_entries()
        if entry_type is not None:
            entries = [e for e in entries if e.type == entry_type]
        if limit is not None:
            entries = entries[-limit:]
        return entries

    def get_entry(self, tome_id: str, entry_id: str) -> TomeEntry | None:
        for entry in self.get_entries(tome_id):
            if entry.id == entry_id:
                return entry
        return None

    def get_leaf_id(self, tome_id: str) -> str | None:
        """The entry the Tome's Leaf currently points at."""
        for entry in reversed(self.get_entries(tome_id)):
            if entry.type == TomeEntryType.LEAF:
                target = entry.payload.get("targetId")
                return str(target) if target is not None else None
        meta = self.open_tome(tome_id)
        if meta is not None and meta.active_leaf_id:
            return meta.active_leaf_id
        return None

    def list_leaves(self, tome_id: str) -> list[str]:
        """Content entries never referenced as another entry's parent."""
        content = [e for e in self.get_entries(tome_id) if e.type != TomeEntryType.LEAF]
        if not content:
            return []
        parent_ids = {e.parent_id for e in content if e.parent_id is not None}
        return [e.id for e in content if e.id not in parent_ids]

    def get_parent_summoner_entry(
        self, tome_id: str, leaf_id: str | None = None
    ) -> TomeEntry | None:
        """Parent of the most recent user message along the leaf branch."""
        target_leaf = leaf_id or self.get_leaf_id(tome_id)
        branch = self.get_entries_for_context(tome_id, leaf_id=target_leaf)
        for entry in reversed(branch):
            if (
                entry.type == TomeEntryType.MESSAGE
                and (entry.payload or {}).get("role") == "user"
            ):
                if entry.parent_id is None:
                    return None
                return self.get_entry(tome_id, entry.parent_id)
        return None

    def get_entries_for_context(
        self,
        tome_id: str,
        leaf_id: str | None = None,
        max_entries: int | None = None,
    ) -> list[TomeEntry]:
        entries = self.get_entries(tome_id)
        if leaf_id:
            entries = _filter_entries_to_leaf(entries, leaf_id)
        if max_entries is not None:
            entries = entries[-max_entries:]
        return entries

    def read_last_n_entries(self, tome_id: str, limit: int) -> list[TomeEntry]:
        if limit <= 0:
            return []
        return self.get_entries(tome_id)[-limit:]

    def verify_integrity(self, tome_id: str) -> TomeIntegrityReport:
        """Audit a tome file without touching any cache."""
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None and Path(tome_id).is_file():
            resolved = self._resolve_tome_id(Path(tome_id).stem)
        target = resolved or _validate_tome_id(tome_id)
        path = self._tome_dir / f"{target}.jsonl"
        if not path.exists():
            return TomeIntegrityReport(
                valid=False,
                tome_id=target,
                issues=[
                    TomeIntegrityIssue(
                        line_number=0,
                        message=f"Tome file does not exist: {path}",
                    )
                ],
            )

        issues: list[TomeIntegrityIssue] = []
        total_lines = 0
        valid_entries_count = 0
        try:
            with path.open("r", encoding="utf-8") as f:
                header_line = f.readline()
                total_lines += 1
                header_raw = header_line.rstrip("\r\n")
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
                    except json.JSONDecodeError as e:
                        header = None
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=1,
                                message=f"Corrupted session header: invalid JSON: {e}",
                                raw_line=header_raw,
                            )
                        )
                    if header is not None:
                        if not isinstance(header, dict):
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=1,
                                    message="Invalid session header: "
                                    "expected JSON object",
                                    raw_line=header_raw,
                                )
                            )
                        else:
                            if header.get("type") != "session":
                                issues.append(
                                    TomeIntegrityIssue(
                                        line_number=1,
                                        message="Invalid session header: "
                                        "missing or invalid 'type' "
                                        f"(expected 'session', got "
                                        f"{header.get('type')!r})",
                                        raw_line=header_raw,
                                    )
                                )
                            if not header.get("id") or not isinstance(
                                header.get("id"), str
                            ):
                                issues.append(
                                    TomeIntegrityIssue(
                                        line_number=1,
                                        message="Invalid session header: missing or "
                                        "invalid 'id'",
                                        raw_line=header_raw,
                                    )
                                )
                            elif header.get("id") != path.stem:
                                issues.append(
                                    TomeIntegrityIssue(
                                        line_number=1,
                                        message=(
                                            "Header ID mismatch: expected "
                                            f"'{path.stem}', got '{header.get('id')}'"
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
                                        message="Invalid session header: missing or "
                                        "invalid 'cwd'",
                                        raw_line=header_raw,
                                    )
                                )
                            if "timestamp" not in header or not isinstance(
                                header.get("timestamp"), str
                            ):
                                issues.append(
                                    TomeIntegrityIssue(
                                        line_number=1,
                                        message="Invalid session header: missing or "
                                        "invalid 'timestamp'",
                                        raw_line=header_raw,
                                    )
                                )
                            version_raw = header.get("version", CURRENT_SESSION_VERSION)
                            try:
                                version = int(version_raw)
                                if version != CURRENT_SESSION_VERSION:
                                    issues.append(
                                        TomeIntegrityIssue(
                                            line_number=1,
                                            message=f"Unsupported session version: "
                                            f"{version}",
                                            raw_line=header_raw,
                                        )
                                    )
                            except (ValueError, TypeError):
                                issues.append(
                                    TomeIntegrityIssue(
                                        line_number=1,
                                        message="Invalid session version: "
                                        f"{version_raw}",
                                        raw_line=header_raw,
                                    )
                                )

                for idx, raw_line in enumerate(f, start=2):
                    total_lines += 1
                    line = raw_line.rstrip("\r\n")
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
                    broken = False
                    if not entry_raw.get("id") or not isinstance(
                        entry_raw.get("id"), str
                    ):
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=idx,
                                message="Malformed entry: missing or invalid 'id' "
                                "field",
                                raw_line=line,
                            )
                        )
                        broken = True
                    entry_type_raw = entry_raw.get("type")
                    if not entry_type_raw or not isinstance(entry_type_raw, str):
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=idx,
                                message="Malformed entry: missing or invalid 'type' "
                                "field",
                                raw_line=line,
                            )
                        )
                        broken = True
                    else:
                        try:
                            TomeEntryType(entry_type_raw)
                        except ValueError:
                            issues.append(
                                TomeIntegrityIssue(
                                    line_number=idx,
                                    message="Malformed entry: invalid entry type "
                                    f"'{entry_type_raw}'",
                                    raw_line=line,
                                )
                            )
                            broken = True
                    ts = entry_raw.get("timestamp")
                    if (
                        ts is None
                        or isinstance(ts, bool)
                        or not isinstance(ts, (int, float))
                    ):
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=idx,
                                message="Malformed entry: missing or invalid "
                                "'timestamp' (must be number)",
                                raw_line=line,
                            )
                        )
                        broken = True
                    payload = entry_raw.get("payload")
                    if payload is not None and not isinstance(payload, dict):
                        issues.append(
                            TomeIntegrityIssue(
                                line_number=idx,
                                message="Malformed entry: 'payload' must be an "
                                "object/dict",
                                raw_line=line,
                            )
                        )
                        broken = True
                    if not broken:
                        valid_entries_count += 1

            return TomeIntegrityReport(
                valid=len(issues) == 0,
                tome_id=target,
                issues=issues,
                total_lines=total_lines,
                valid_entries_count=valid_entries_count,
            )
        except OSError as e:
            return TomeIntegrityReport(
                valid=False,
                tome_id=target,
                issues=[
                    TomeIntegrityIssue(
                        line_number=0, message=f"Failed to read file: {e}"
                    )
                ],
            )

    def replay_tome_trajectory(self, tome_id: str) -> list[ATIFTrajectoryStep]:
        """Convert session active branch to sequential list of ATIF trajectory steps."""
        meta = self.open_tome(tome_id)
        leaf_id = self.get_leaf_id(tome_id)
        branch = self.get_entries_for_context(tome_id, leaf_id=leaf_id)

        steps: list[ATIFTrajectoryStep] = []
        prev_timestamp: float | None = None

        for entry in branch:
            if entry.type != TomeEntryType.MESSAGE:
                continue

            payload = entry.payload or {}
            raw_role = payload.get("role", "")
            raw_content = payload.get("content", "")

            role: str
            content_str: str = ""
            tool_calls: list[dict[str, Any]] = []
            tool_call_id: str | None = None
            reasoning_content: str | None = None
            step_model = payload.get("model") or (meta.model if meta else None)

            if raw_role == "user":
                role = "user"
                if isinstance(raw_content, str):
                    content_str = raw_content
                elif isinstance(raw_content, list):
                    texts = [
                        block.get("text", "")
                        for block in raw_content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    content_str = "\n".join(texts)
                else:
                    content_str = str(raw_content)

            elif raw_role == "assistant":
                role = "assistant"
                if isinstance(raw_content, str):
                    content_str = raw_content
                elif isinstance(raw_content, list):
                    text_parts: list[str] = []
                    reasoning_parts: list[str] = []
                    for block in raw_content:
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type", "")
                        if block_type == "text":
                            text_parts.append(block.get("text", ""))
                        elif block_type in ("contemplation", "thinking"):
                            reasoning_parts.append(
                                block.get("thinking") or block.get("text") or ""
                            )
                        elif block_type in ("spell_cast", "tool_use"):
                            tool_calls.append(
                                {
                                    "id": block.get("id", ""),
                                    "name": (
                                        block.get("spell") or block.get("name") or ""
                                    ),
                                    "args": (
                                        block.get("args") or block.get("input") or {}
                                    ),
                                }
                            )
                    content_str = "\n".join(text_parts)
                    if reasoning_parts:
                        reasoning_content = "\n".join(reasoning_parts)
                else:
                    content_str = str(raw_content)

            elif raw_role in ("spellResult", "tool"):
                role = "tool"
                tool_call_id = payload.get("spell_cast_id") or payload.get(
                    "tool_call_id"
                )
                if isinstance(raw_content, str):
                    content_str = raw_content
                elif isinstance(raw_content, list):
                    texts = [
                        b.get("text", "")
                        for b in raw_content
                        if isinstance(b, dict) and "text" in b
                    ]
                    content_str = "\n".join(texts) if texts else json.dumps(raw_content)
                else:
                    content_str = (
                        json.dumps(raw_content)
                        if isinstance(raw_content, (dict, list))
                        else str(raw_content)
                    )
            else:
                continue

            latency_ms = 0.0
            if prev_timestamp is not None and entry.timestamp >= prev_timestamp:
                latency_ms = round((entry.timestamp - prev_timestamp) * 1000.0, 2)
            prev_timestamp = entry.timestamp

            steps.append(
                ATIFTrajectoryStep(
                    step_id=entry.id,
                    role=role,
                    content=content_str,
                    tool_calls=tool_calls,
                    tool_call_id=tool_call_id,
                    timestamp=entry.timestamp,
                    latency_ms=latency_ms,
                    model=step_model,
                    reasoning_content=reasoning_content,
                )
            )

        return steps

    def export_atif_trajectory(
        self,
        tome_id: str,
        agent_name: str = "coding_mvge",
    ) -> dict[str, Any]:
        """Export session trajectory conforming to ATIF."""
        resolved = self._resolve_tome_id(tome_id)
        if resolved is None and Path(tome_id).is_file():
            resolved = self._resolve_tome_id(Path(tome_id).stem)
        target = resolved or _validate_tome_id(tome_id)

        meta = self.open_tome(target)
        steps = self.replay_tome_trajectory(target)

        # Aggregate metrics from messages along the active branch
        input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0

        leaf_id = self.get_leaf_id(target)
        branch = self.get_entries_for_context(target, leaf_id=leaf_id)
        for entry in branch:
            if entry.type == TomeEntryType.MESSAGE:
                payload = entry.payload or {}
                mana = payload.get("mana_usage") or payload.get("usage") or {}
                in_tok = int(mana.get("prompt_tokens") or mana.get("input_tokens") or 0)
                out_tok = int(
                    mana.get("completion_tokens") or mana.get("output_tokens") or 0
                )
                reason_tok = int(
                    mana.get("reasoning_tokens")
                    or mana.get("contemplation_tokens")
                    or 0
                )
                input_tokens += in_tok
                output_tokens += out_tok
                reasoning_tokens += reason_tok

        metrics = ATIFMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            reasoning_tokens=reasoning_tokens,
        )

        trajectory = ATIFTrajectory(
            trajectory_id=target,
            agent_name=agent_name,
            model=meta.model if meta and meta.model else "",
            created_at=meta.created_at if meta else datetime.now(UTC).isoformat(),
            steps=steps,
            metrics=metrics,
            completed=True,
        )

        return trajectory.to_dict()
