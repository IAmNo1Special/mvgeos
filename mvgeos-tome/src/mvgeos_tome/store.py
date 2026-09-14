from __future__ import annotations

import threading
from pathlib import Path
from weakref import WeakValueDictionary

from mvgeos_tome.handle import TomeHandle, TomeHandleFactory


class TomeStore:
    """Stateless factory. No global mutable state - AGENTS.md compliant."""

    def __init__(self) -> None:
        # Weak cache: only live handles prevent GC. No cleanup needed.
        self._handles: WeakValueDictionary[tuple[Path, str, str], TomeHandle] = (
            WeakValueDictionary()
        )
        self._lock = threading.Lock()

    def _canonical(self, tome_dir: Path) -> Path:
        return Path(tome_dir).expanduser().resolve()

    def open(self, tome_dir: Path, tome_id: str, mode: str = "r") -> TomeHandle:
        """Get or create handle. Same (dir, id, mode) -> same handle (identity)."""
        cdir = self._canonical(tome_dir)
        key = (cdir, tome_id, mode)
        with self._lock:
            handle = self._handles.get(key)
            if handle is not None:
                return handle
            handle = TomeHandle(cdir, tome_id, mode)
            self._handles[key] = handle
            return handle

    def list_tomes(self, tome_dir: Path) -> list[str]:
        """List all tome IDs in directory. No caching - always scans."""
        cdir = self._canonical(tome_dir)
        if not cdir.exists():
            return []
        return [f.stem for f in cdir.glob("*.jsonl") if f.is_file()]

    def factory(self, tome_dir: Path) -> TomeHandleFactory:
        """Get a factory for creating/managing tomes in this directory."""
        return TomeHandleFactory(self._canonical(tome_dir))

    # For tests only
    def _clear_weak_cache(self) -> None:
        with self._lock:
            self._handles.clear()


# Default store instance for convenience
_default_store: TomeStore | None = None


def get_default_store() -> TomeStore:
    global _default_store
    if _default_store is None:
        _default_store = TomeStore()
    return _default_store


def reset_default_store() -> None:
    global _default_store
    if _default_store is not None:
        _default_store._clear_weak_cache()
        _default_store = None
