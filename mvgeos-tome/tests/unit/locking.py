import os
import socket
import tempfile
from pathlib import Path

import filelock
import pytest

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.locking import (
    FileLock,
    LockMetadata,
    _is_posix_process_alive,
    is_process_alive,
)


def test_lock_path_normalization(tmp_path: Path) -> None:
    lock1 = FileLock(tmp_path / "tome")
    assert lock1.path == tmp_path / "tome.lock"

    lock2 = FileLock(Path(tmp_path / "tome"))
    assert lock2.path == tmp_path / "tome.lock"

    lock3 = FileLock(tmp_path / ".lock")
    assert lock3.path == tmp_path / ".lock"
    assert not str(lock3.path).endswith(".lock.lock")

    lock4 = FileLock(Path(tmp_path / ".lock"))
    assert lock4.path == tmp_path / ".lock"

    lock5 = FileLock(Path(tmp_path / "tome.lock"))
    assert lock5.path == tmp_path / "tome.lock"


def test_filelock_instance_created_in_init(tmp_path: Path) -> None:
    lock = FileLock(tmp_path / "test")
    assert lock._lock is not None
    assert isinstance(lock._lock, filelock.FileLock)

    initial_lock_obj = lock._lock
    lock.acquire()
    assert lock._lock is initial_lock_obj
    lock.release()
    assert lock._lock is initial_lock_obj


def test_filelock_context_managers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "test.lock"
        lock = FileLock(lock_path)
        with lock:
            assert lock_path.exists()


@pytest.mark.asyncio
async def test_filelock_async_context_manager() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "test_async.lock"
        lock = FileLock(lock_path)
        async with lock:
            assert lock_path.exists()


def test_ledger_uses_normalized_lock_path() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tome_dir = Path(tmpdir)
        ledger = TomeLedger(tome_dir)
        assert ledger._lock.path == tome_dir / ".lock"
        assert not str(ledger._lock.path).endswith(".lock.lock")


def test_lock_metadata_serialization() -> None:
    meta = LockMetadata(pid=12345, timestamp=1700000000.0, host="test-host")
    data = meta.to_dict()
    assert data == {"pid": 12345, "timestamp": 1700000000.0, "host": "test-host"}

    restored = LockMetadata.from_dict(data)
    assert restored.pid == 12345
    assert restored.timestamp == 1700000000.0
    assert restored.host == "test-host"

    json_str = meta.to_json()
    from_json_meta = LockMetadata.from_json(json_str)
    assert from_json_meta == meta
    assert LockMetadata.from_json("invalid json") is None
    assert LockMetadata.from_json("{}") is None


def test_is_process_alive() -> None:
    assert is_process_alive(os.getpid()) is True
    assert is_process_alive(os.getpid(), socket.gethostname()) is True
    # Non-existent PID
    assert is_process_alive(99999999) is False
    assert is_process_alive(-1) is False
    # Foreign host: fail-safe assume alive
    assert is_process_alive(99999999, "foreign-host-xyz") is True


def test_filelock_writes_and_cleans_metadata(tmp_path: Path) -> None:
    lock_path = tmp_path / "session.lock"
    lock = FileLock(lock_path)
    assert lock.read_metadata() is None

    with lock:
        meta = lock.read_metadata()
        assert meta is not None
        assert meta.pid == os.getpid()
        assert meta.host == socket.gethostname()
        assert meta.timestamp > 0
        assert lock.metadata_path.exists()

    # After exit, metadata should be cleaned up
    assert lock.read_metadata() is None
    assert not lock.metadata_path.exists()


def test_filelock_is_stale_detection(tmp_path: Path) -> None:
    lock_path = tmp_path / "stale_test.lock"
    lock = FileLock(lock_path)
    assert lock.is_stale() is False

    # Simulate live process metadata
    live_meta = LockMetadata(
        pid=os.getpid(), timestamp=100.0, host=socket.gethostname()
    )
    lock.metadata_path.write_text(live_meta.to_json(), encoding="utf-8")
    assert lock.is_stale() is False

    # Simulate dead process metadata
    dead_meta = LockMetadata(pid=99999999, timestamp=100.0, host=socket.gethostname())
    lock.metadata_path.write_text(dead_meta.to_json(), encoding="utf-8")
    assert lock.is_stale() is True


def test_filelock_force_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "force_test.lock"
    lock = FileLock(lock_path)
    dead_meta = LockMetadata(pid=99999999, timestamp=100.0, host="local")
    lock.path.write_text("lock", encoding="utf-8")
    lock.metadata_path.write_text(dead_meta.to_json(), encoding="utf-8")

    assert lock.path.exists()
    assert lock.metadata_path.exists()

    lock.force_release()
    assert not lock.path.exists()
    assert not lock.metadata_path.exists()


def test_filelock_force_release_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "stale_release.lock"
    lock = FileLock(lock_path)
    dead_meta = LockMetadata(pid=99999999, timestamp=100.0, host=socket.gethostname())
    lock.path.write_text("lock", encoding="utf-8")
    lock.metadata_path.write_text(dead_meta.to_json(), encoding="utf-8")

    released = lock.force_release_stale()
    assert released is True
    assert not lock.path.exists()
    assert not lock.metadata_path.exists()

    # When no lock or live lock, returns False
    assert lock.force_release_stale() is False


def test_filelock_acquire_recovers_stale_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "recover.lock"
    lock = FileLock(lock_path, timeout=0.1)

    # Place a stale lock held by a dead process
    dead_meta = LockMetadata(pid=99999999, timestamp=100.0, host=socket.gethostname())
    lock.path.write_text("dummy", encoding="utf-8")
    lock.metadata_path.write_text(dead_meta.to_json(), encoding="utf-8")

    # Acquire should detect stale lock, recover it, and succeed
    lock.acquire()
    try:
        new_meta = lock.read_metadata()
        assert new_meta is not None
        assert new_meta.pid == os.getpid()
    finally:
        lock.release()


def test_tome_ledger_init_cleans_stale_locks(tmp_path: Path) -> None:
    tome_dir = tmp_path / "tomes"
    tome_dir.mkdir()
    stale_lock = tome_dir / ".lock"
    stale_meta = tome_dir / ".lock.meta"
    stale_lock.write_text("lock", encoding="utf-8")
    dead_meta = LockMetadata(pid=99999999, timestamp=100.0, host=socket.gethostname())
    stale_meta.write_text(dead_meta.to_json(), encoding="utf-8")

    # Initializing TomeLedger should clean up stale lock
    ledger = TomeLedger(tome_dir)
    assert not stale_meta.exists()
    # Ledger should be functional and able to acquire lock
    meta = ledger.create_tome(str(tmp_path))
    assert meta.id is not None


def test_filelock_acquire_timeout_on_live_process(tmp_path: Path) -> None:
    lock1 = FileLock(tmp_path / "live.lock", timeout=1.0)
    lock2 = FileLock(tmp_path / "live.lock", timeout=0.05)

    with lock1, pytest.raises(filelock.Timeout):
        lock2.acquire()


def test_lock_metadata_invalid_payloads(tmp_path: Path) -> None:
    assert LockMetadata.from_json("12345") is None
    assert LockMetadata.from_json('{"pid": 123}') is None
    assert LockMetadata.from_json('{"pid": 123, "timestamp": 100.0}') is None
    assert LockMetadata.from_json('{"pid": "bad", "timestamp": 1, "host": "h"}') is None

    lock = FileLock(tmp_path / "corrupt.lock")
    lock.metadata_path.write_text("not json", encoding="utf-8")
    assert lock.read_metadata() is None


def test_is_process_alive_permission_and_os_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_kill_permission(pid: int, sig: int) -> None:
        raise PermissionError("Access denied")

    monkeypatch.setattr(os, "kill", fake_kill_permission)
    assert _is_posix_process_alive(12345) is True

    def fake_kill_oserror(pid: int, sig: int) -> None:
        raise OSError("Unknown error")

    monkeypatch.setattr(os, "kill", fake_kill_oserror)
    assert _is_posix_process_alive(12345) is False


def test_tome_ledger_cleans_multiple_and_orphaned_locks(tmp_path: Path) -> None:
    tome_dir = tmp_path / "multi_tomes"
    tome_dir.mkdir()

    # Create multiple stale locks and orphaned meta
    dead_meta = LockMetadata(pid=99999999, timestamp=100.0, host=socket.gethostname())
    (tome_dir / "session1.lock").write_text("lock", encoding="utf-8")
    (tome_dir / "session1.lock.meta").write_text(dead_meta.to_json(), encoding="utf-8")

    (tome_dir / "orphaned.lock.meta").write_text(dead_meta.to_json(), encoding="utf-8")

    ledger = TomeLedger(tome_dir)
    assert not (tome_dir / "session1.lock.meta").exists()
    assert not (tome_dir / "orphaned.lock.meta").exists()
    assert ledger.dir == tome_dir


def test_filelock_write_metadata_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = FileLock(tmp_path / "write_err.lock")

    def fake_write_text(self: Path, *args: object, **kwargs: object) -> int:
        raise OSError("Disk full")

    monkeypatch.setattr(Path, "write_text", fake_write_text)
    # Should not raise exception
    lock.acquire()
    lock.release()


def test_tome_ledger_cleanup_stale_locks_exception_handling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tome_dir = tmp_path / "error_tomes"
    tome_dir.mkdir()
    (tome_dir / ".lock").write_text("lock", encoding="utf-8")

    def fake_force_release_stale(self: FileLock) -> bool:
        raise RuntimeError("Lock cleanup failure")

    monkeypatch.setattr(FileLock, "force_release_stale", fake_force_release_stale)
    # Initialization should catch exception and not fail
    ledger = TomeLedger(tome_dir)
    assert ledger.dir == tome_dir
