from __future__ import annotations

import ctypes
import json
import logging
import os
import socket
import sys
import time
from contextlib import suppress
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import filelock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LockMetadata:
    pid: int
    timestamp: float
    host: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockMetadata:
        return cls(
            pid=int(data["pid"]),
            timestamp=float(data["timestamp"]),
            host=str(data["host"]),
        )

    @classmethod
    def from_json(cls, json_str: str) -> LockMetadata | None:
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return None
            if "pid" not in data or "timestamp" not in data or "host" not in data:
                return None
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None


def _is_windows_process_alive(pid: int) -> bool:
    try:
        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        still_active = 259
        wait_timeout = 0x102
        wait_object_0 = 0

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        kernel32 = windll.kernel32
        handle = kernel32.OpenProcess(
            process_query_limited_information | synchronize,
            False,
            wintypes.DWORD(pid),
        )
        if not handle:
            return False
        try:
            wait_res = kernel32.WaitForSingleObject(handle, 0)
            if wait_res == wait_timeout:
                return True
            if wait_res == wait_object_0:
                return False

            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return int(exit_code.value) == still_active
            return False
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, ValueError):
        return False


def _is_posix_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def is_process_alive(pid: int, host: str | None = None) -> bool:
    """Check if a process with the given PID is alive on the local host."""
    if pid <= 0:
        return False
    if host is not None and host != socket.gethostname():
        # Cross-host process liveness cannot be verified locally; assume alive
        return True

    if sys.platform == "win32":
        return _is_windows_process_alive(pid)
    else:
        return _is_posix_process_alive(pid)


class FileLock:
    def __init__(self, path: str | Path, timeout: float = 30.0) -> None:
        p = Path(path)
        if p.name.endswith(".lock"):
            self._path = p
        else:
            self._path = p.with_name(p.name + ".lock")
        self._meta_path = self._path.with_name(self._path.name + ".meta")
        self._timeout = timeout
        self._lock = filelock.FileLock(self._path, timeout=self._timeout)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def metadata_path(self) -> Path:
        return self._meta_path

    def read_metadata(self) -> LockMetadata | None:
        if not self._meta_path.exists():
            return None
        try:
            content = self._meta_path.read_text(encoding="utf-8")
            return LockMetadata.from_json(content)
        except (OSError, ValueError):
            return None

    def _write_metadata(self) -> None:
        meta = LockMetadata(
            pid=os.getpid(),
            timestamp=time.time(),
            host=socket.gethostname(),
        )
        try:
            self._meta_path.parent.mkdir(parents=True, exist_ok=True)
            self._meta_path.write_text(meta.to_json(), encoding="utf-8")
        except OSError as e:
            logger.warning(
                "Failed to write lock metadata to %s: %s", self._meta_path, e
            )

    def _clear_metadata(self) -> None:
        with suppress(OSError):
            if self._meta_path.exists():
                self._meta_path.unlink()

    def is_stale(self) -> bool:
        meta = self.read_metadata()
        if meta is None:
            return False
        return not is_process_alive(meta.pid, meta.host)

    def force_release(self) -> None:
        self._clear_metadata()
        with suppress(OSError):
            if self._path.exists():
                self._path.unlink()
        self._lock = filelock.FileLock(self._path, timeout=self._timeout)

    def force_release_stale(self) -> bool:
        if self.is_stale():
            logger.warning(
                "Force-releasing stale lock held by defunct process: %s",
                self._path,
            )
            self.force_release()
            return True
        return False

    def acquire(self, timeout: float | None = None) -> None:
        target_timeout = timeout if timeout is not None else self._timeout
        try:
            self._lock.acquire(timeout=target_timeout)
            self._write_metadata()
        except filelock.Timeout:
            if self.is_stale():
                logger.warning(
                    "Detected stale lock on timeout (%s). Recovering...",
                    self._path,
                )
                self.force_release()
                self._lock.acquire(timeout=target_timeout)
                self._write_metadata()
            else:
                raise

    def release(self) -> None:
        self._clear_metadata()
        with suppress(OSError):
            self._lock.release()

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(
        self, _exc: type[BaseException] | None, _val: BaseException | None, _tb: Any
    ) -> None:
        self.release()

    async def __aenter__(self) -> FileLock:
        self.acquire()
        return self

    async def __aexit__(
        self, _exc: type[BaseException] | None, _val: BaseException | None, _tb: Any
    ) -> None:
        self.release()
