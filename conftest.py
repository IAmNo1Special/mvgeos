"""TEMPORARY diagnostic probe for the macOS crossplatform hang. DO NOT MERGE.

v1 armed faulthandler under pytest capture: the dump was silently lost
(pytest replaces sys.stderr with a BytesIO-backed object, no real fd).

v2 wrote with os.write() to fds 1/2, but pytest's default fd-level capture
dup2's fds 1/2 to temp files during tests, so the output died with the
process. Proven locally.

v3: pytest suspends its global fd capture around pytest_sessionstart, so
os.dup(1)/os.dup(2) there capture the REAL fds (proven locally: writes via
the saved fds from inside a test reach the real stderr with capture on).
The watchdog writes heartbeats and the final all-threads dump through the
saved fds, then os._exit(1) for a fast job failure with the traceback
in the log.
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
_real_fds = {}


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


def _emit(msg: bytes) -> None:
    fd = _real_fds.get(2, 2)
    try:
        os.write(fd, msg)
    except OSError:
        pass


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
            _emit(
                f"[watchdog] alive; idle {idle:.0f}s; "
                f"last test start: {nodeid}\n".encode()
            )
        if idle >= _TIMEOUT_S:
            _emit(
                f"\n[watchdog] FIRING: no test started for {idle:.0f}s "
                f"(last: {nodeid}). Dumping all thread stacks.\n".encode()
            )
            try:
                _emit(_dump_all_threads())
            except Exception as exc:  # noqa: BLE001 - diagnostic only
                _emit(f"[watchdog] stack dump failed: {exc!r}\n".encode())
            _emit(b"[watchdog] exiting process now.\n")
            os._exit(1)


def pytest_sessionstart(session) -> None:  # noqa: ARG001 - hook signature
    # Global fd capture is suspended during sessionstart: these are the
    # real fds. (Proven locally; dup'ing at conftest import instead
    # captures pytest's capture temp file.)
    _real_fds[1] = os.dup(1)
    _real_fds[2] = os.dup(2)
    t = threading.Thread(target=_watchdog, name="hang-watchdog", daemon=True)
    t.start()


def pytest_runtest_logstart(nodeid, location) -> None:  # noqa: ARG001 - hook signature
    _note_logstart(nodeid)
