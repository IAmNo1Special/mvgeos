from __future__ import annotations

from pathlib import Path
from typing import Any

import filelock


class FileLock:
    def __init__(self, path: str | Path, timeout: float = 30.0) -> None:
        p = Path(path)
        if p.name.endswith(".lock"):
            self._path = p
        else:
            self._path = p.with_name(p.name + ".lock")
        self._timeout = timeout
        self._lock = filelock.FileLock(self._path, timeout=self._timeout)

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> None:
        self._lock.acquire()

    def release(self) -> None:
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
