import tempfile
from pathlib import Path

import filelock
import pytest

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.locking import FileLock


def test_lock_path_normalization() -> None:
    lock1 = FileLock("dir/tome")
    assert lock1.path == Path("dir/tome.lock")

    lock2 = FileLock(Path("dir/tome"))
    assert lock2.path == Path("dir/tome.lock")

    lock3 = FileLock("dir/.lock")
    assert lock3.path == Path("dir/.lock")
    assert not str(lock3.path).endswith(".lock.lock")

    lock4 = FileLock(Path("dir/.lock"))
    assert lock4.path == Path("dir/.lock")

    lock5 = FileLock(Path("dir/tome.lock"))
    assert lock5.path == Path("dir/tome.lock")


def test_filelock_instance_created_in_init() -> None:
    lock = FileLock("dir/test")
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
