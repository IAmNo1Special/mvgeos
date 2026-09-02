import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from ctypes import wintypes
from pathlib import Path

from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.locking import FileLock
from mvgeos_tome.types import TomeEntry, TomeEntryType


def _kill_pid(pid: int) -> None:
    if sys.platform == "win32":
        windll = getattr(ctypes, "windll", None)
        if windll:
            kernel32 = windll.kernel32
            process_terminate = 0x0001
            handle = kernel32.OpenProcess(process_terminate, False, wintypes.DWORD(pid))
            if handle:
                try:
                    kernel32.TerminateProcess(handle, 1)
                finally:
                    kernel32.CloseHandle(handle)
    else:
        with suppress(OSError):
            os.kill(pid, signal.SIGKILL)


def test_subprocess_crash_recovery() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tome_dir = Path(tmpdir)
        lock_path = tome_dir / ".lock"

        # Child process script that acquires lock, writes metadata, and signals
        child_code = (
            "import os, time, sys\n"
            "from pathlib import Path\n"
            "from mvgeos_tome.locking import FileLock\n"
            f"lock = FileLock(Path(r'{lock_path}'))\n"
            "lock.acquire()\n"
            "print(f'LOCKED {os.getpid()}', flush=True)\n"
            "time.sleep(30)\n"
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", child_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        child_pid: int | None = None
        try:
            # Wait for child to acquire lock
            assert proc.stdout is not None
            line = proc.stdout.readline().strip()
            assert line.startswith("LOCKED")
            child_pid = int(line.split()[1])

            # Verify lock metadata exists and matches child process
            lock = FileLock(lock_path)
            meta = lock.read_metadata()
            assert meta is not None
            assert meta.pid == child_pid

            # Simulate abrupt process crash / kill
            _kill_pid(child_pid)
            proc.kill()
            proc.wait()

            # Small wait to ensure OS has reclaimed process handle
            time.sleep(0.1)

            # Now verify stale lock recovery in parent
            assert lock.is_stale() is True

            # TomeLedger initialization should clean up stale lock and operate normally
            ledger = TomeLedger(tome_dir)
            tome_meta = ledger.create_tome(str(tome_dir))
            assert tome_meta.id is not None

            # Append entry to confirm lock acquisition and ledger mutation work
            entry = TomeEntry(
                id="entry-1",
                parent_id=None,
                type=TomeEntryType.MESSAGE,
                timestamp=time.time(),
                payload={"text": "recovered"},
            )
            ledger.append(tome_meta.id, entry)

            entries = ledger.get_entries(tome_meta.id)
            assert len(entries) == 1
            assert entries[0].payload == {"text": "recovered"}
        finally:
            if child_pid is not None:
                _kill_pid(child_pid)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
