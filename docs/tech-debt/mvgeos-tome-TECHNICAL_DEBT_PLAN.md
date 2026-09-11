# mvgeos-tome Technical Debt Remediation Plan

---

## Issue Index

| ID | Title | Priority | Effort | Status |
|----|-------|----------|--------|--------|
| TOME-002 | Full file loading in `_read_tome_entries_from_disk` | High | Medium | [RESOLVED] Implemented via `iter_tome_entries` |
| TOME-003 | `FileLock` has no stale lock recovery | High | Medium | [RESOLVED] Implemented via `force_release_stale` |
| TOME-005 | No session file integrity check (CRC/checksum) | Medium | Small | [RESOLVED] Implemented via `verify_integrity` |
| TOME-008 | Session version migration logic | Medium | Medium | Open |

---

## Issue 1: Full File Loading in `_read_tome_entries_from_disk`
**ID**: TOME-002  
**Priority**: High  
**Effort**: Medium  
**Dependencies**: None

### Root Cause Analysis
`_read_tome_entries_from_disk()` at `ledger.py:399-401` loads the entire file into memory with `f.readlines()`:
```python
with tome_file.open("r", encoding="utf-8") as f:
    lines = f.readlines()
```
For large session files (100MB+), this causes $O(n)$ memory spikes.

### Fix Steps
1. **Add streaming line iterator** in `TomeLedger`:
   - `def iter_tome_entries(self, tome_id: str) -> Generator[TomeEntry]`
   - Yield entries line-by-line using a generator.
2. **Add tail reader helper** `read_last_n_entries(tome_id: str, limit: int)` for bounded context recovery.

### Testing
- Memory profiling test with large JSONL sessions
- Benchmark streaming iteration vs full load

---

## Issue 2: `FileLock` Has No Recovery Mechanism
**ID**: TOME-003  
**Priority**: High  
**Effort**: Medium  
**Dependencies**: None

### Root Cause Analysis
`FileLock` at `locking.py:9-45` wraps `filelock.FileLock` but has no crash recovery:
- If a process crashes or is forcefully terminated while holding the lock, `.lock` may remain on disk.
- No stale lock detection (no PID/timestamp metadata in lock file).
- `timeout=30.0` waits but cannot recover from stale locks left by defunct processes.

### Fix Steps
1. **Add stale lock detection**:
   - Write acquiring PID + timestamp + hostname into lock file.
   - On lock contention timeout, verify if holding process is still alive (`os.kill(pid, 0)` on POSIX / `OpenProcess` check on Windows).
   - If holding process no longer exists, force-release the stale lock.
2. **Add `force_release_stale()` method** called during `TomeLedger.__init__()`.

### Testing
- Simulate process termination while holding lock; verify automatic recovery on next access.

---

## Issue 3: No Session File Integrity Check (CRC/Checksum)
**ID**: TOME-005  
**Priority**: Medium  
**Effort**: Small  
**Dependencies**: None

### Root Cause Analysis
`TomeLedger._read_tome_entries_from_disk()` calls `json.loads(line)` without verification. Corrupted lines (truncated writes, disk corruption) raise `json.JSONDecodeError` and can break session loading mid-stream.

### Fix Steps
1. **Add CRC32 checksum per JSONL entry**:
   - Format: `{json}\t{crc32:08x}\n` or embedded in payload.
   - Skip/flag corrupted lines gracefully during reads.
2. **Add session-level checksum in header** (SHA256 of metadata).
3. **Add `verify_integrity(tome_id: str)` method** returning `(valid: bool, errors: list[tuple[int, str]])`.

### Testing
- Corrupt JSONL file (truncated line, corrupted bytes) and verify graceful recovery/warning.

---

## Issue 4: Session Version Migration
**ID**: TOME-008  
**Priority**: Medium  
**Effort**: Medium  
**Dependencies**: TOME-005

### Root Cause Analysis
`TomeLedger._write_tome_file` writes `"version": 3`, but no automated schema migration logic exists for reading v1/v2 format files into the current schema.

### Fix Steps
1. **Add version detection in `TomeLedger._load_tome_metadata()`**:
   - Read `header.get("version", 1)`
2. **Implement migration pipeline**:
   - `_migrate_v1_to_v2(header, entries)`
   - `_migrate_v2_to_v3(header, entries)`
   - Auto-upgrade older session files on read

### Testing
- Test migration round-trip from v1, v2 fixtures to v3 format.

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| TOME-002 | None | — |
| TOME-003 | None | — |
| TOME-005 | None | TOME-008 |
| TOME-008 | TOME-005 | — |

---

## Implementation Order (Recommended)

1. **TOME-003** (Lock recovery) — High impact, reliability
2. **TOME-005** (Integrity checks) — Medium, enables safe migration
3. **TOME-002** (Streaming reads) — Memory optimization
4. **TOME-008** (Version migration) — Format stability

---

## Testing Strategy

- Unit tests in `mvgeos-tome/tests/`
- Full session lifecycle integration tests (create -> append -> branch -> compact)
- Crash recovery simulation for `FileLock`
- Run: `uv run python -m pytest mvgeos-tome/tests/ --cov`

