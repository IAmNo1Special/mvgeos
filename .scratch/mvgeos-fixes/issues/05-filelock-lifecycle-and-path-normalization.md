# 05 — Refactor FileLock lifecycle and normalize lock file paths

**What to build:** Refactor `FileLock` in `mvgeos-tome/mvgeos_tome/locking.py` to instantiate `filelock.FileLock` once in `__init__`, normalize paths using `pathlib.Path` to prevent duplicate `.lock.lock` files, and eliminate raw string concatenation.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `FileLock` normalizes paths with `pathlib.Path` so lock files resolve to `tome_dir / ".lock"` without appending `.lock.lock`.
- [ ] `filelock.FileLock` instance is created once during `FileLock.__init__` and reused across `acquire()` and `release()` calls.
- [ ] All file path operations in `locking.py` use `pathlib.Path`.
- [ ] Unit and integration tests in `mvgeos-tome/tests/` verify lock acquisition, release, and single `.lock` file extension.
