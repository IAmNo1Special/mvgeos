"""TEMPORARY diagnostic probe for the macOS crossplatform hang. DO NOT MERGE.

v1 used faulthandler.dump_traceback_later armed from pytest_runtest_logstart.
That silently lost the dump: pytest's capture replaces sys.stderr with a
BytesIO-backed object, so faulthandler had no real fd to write to, then
_exit(1) killed the job with no traceback (proven locally).

v2 bypasses capture entirely: the watchdog thread writes with os.write()
straight to the real fds 1/2, which pytest's sys.stdout/sys.stderr
replacement cannot intercept. Thread stacks come from sys._current_frames()
so no faulthandler fd is involved at all.
"""

import os
import sys
import threading
import time
import traceback

_TIMEOUT_S = 240
_HEARTBEAT_S = 60

_last_logstart = time.monotonic()
_last_nodeid = "<session start>"
_lock = threading.Lock()


def _note_logstart(nodeid: str) -> None:
    global _last_logstart, _last_nodeid
    with _lock:
        _last_logstart = time.monotonic()
        _last_nodeid = nodeid


def _dump_all_threads() -> bytes:
    out = []
    for thread_id, frame in sys._current_frames().items():
        out.append(f"\n--- Thread {thread_id} ---")
        out.append("".join(traceback.format_stack(frame)))
    return "".join(out).encode("utf-8", "replace")


def _watchdog() -> None:
    last_beat = time.monotonic()
    while True:
        time.sleep(5)
        now = time.monotonic()
        with _lock:
            idle = now - _last_logstart
            nodeid = _last_nodeid
        if now - last_beat >= _HEARTBEAT_S:
            last_beat = now
            os.write(
                2,
                f"[watchdog] alive; idle {idle:.0f}s; last test start: {nodeid}\n".encode(),
            )
        if idle >= _TIMEOUT_S:
            os.write(
                2,
                f"\n[watchdog] FIRING: no test started for {idle:.0f}s "
                f"(last: {nodeid}). Dumping all thread stacks.\n".encode(),
            )
            try:
                os.write(2, _dump_all_threads())
            except Exception as exc:  # noqa: BLE001 - diagnostic only
                os.write(2, f"[watchdog] stack dump failed: {exc!r}\n".encode())
            os.write(2, b"[watchdog] exiting process now.\n")
            os._exit(1)


def pytest_sessionstart(session) -> None:  # noqa: ARG001 - hook signature
    t = threading.Thread(target=_watchdog, name="hang-watchdog", daemon=True)
    t.start()


def pytest_runtest_logstart(nodeid, location) -> None:  # noqa: ARG001 - hook signature
    _note_logstart(nodeid)
