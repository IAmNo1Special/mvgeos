from __future__ import annotations

from typing import Any

pass


class FileLock:
    def __init__(self, path: str, timeout: float = 30.0) -> None:
        self._path = path
        self._timeout = timeout
        self._lock: Any | None = None

    def acquire(self) -> None:
        import filelock

        self._lock = filelock.FileLock(self._path + ".lock", timeout=self._timeout)
        self._lock.acquire()

    def release(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None

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
