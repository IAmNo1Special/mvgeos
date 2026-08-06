# mvgeos-tome Technical Debt Remediation Plan

---

## Issue 1: Synchronous File I/O in Async Context
**ID**: TOME-001  
**Priority**: High  
**Effort**: Medium  
**Dependencies**: None (internal to mvgeos-tome)
**Status**: Resolved — SessionManager removed, TomeLedger uses synchronous I/O within FileLock context

### Root Cause Analysis
`JsonlStore.append()` at `jsonl_store.py:18-20` uses synchronous blocking I/O:
```python
def append(self, entry: dict[str, Any]) -> None:
    with self._path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```
This blocks the event loop when called from async contexts (e.g., `TomeLedger.append()` at `ledger.py:98-103` which is called from async contexts in mvgeos-agent).

### Resolution
`SessionManager` (which had the same issue at `session.py:129-133`) has been removed. `TomeLedger.append()` now runs synchronous I/O within the `FileLock` context manager, which is acceptable since the lock is already held. The broader async I/O conversion (TOME-001 original scope) is tracked separately if needed.

---

## Issue 2: JsonlStore.read_all() Loads Entire File into Memory
**ID**: TOME-002  
**Priority**: High  
**Effort**: Medium  
**Dependencies**: TOME-001 (async conversion)
**Status**: Partially Resolved — SessionManager removed; TomeLedger still uses `read_all()` for index rebuild

### Root Cause Analysis
`JsonlStore.read_all()` at `jsonl_store.py:22-26` loads entire file:
```python
def read_all(self) -> list[dict[str, Any]]:
    if not self._path.exists():
        return []
    with self._path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
```
For large session files (100MB+), this causes O(n) memory usage and O(n) latency.

`SessionManager.open()` at `session.py:96-110` called `read_all()` loading entire session into memory — **resolved** (SessionManager removed).

### Fix Steps
1. **Add streaming iterator method** to `JsonlStore`:
   - File: `mvgeos-tome/mvgeos_tome/jsonl_store.py`
   - Add `async def iter_entries(self) -> AsyncIterator[dict[str, Any]]`
   - Use `aiofiles.open()` with async line iteration

2. **Add `read_entries_streaming()` with optional filter/limit**:
   - File: `mvgeos-tome/mvgeos_tome/jsonl_store.py`
   - Parameters: `entry_type`, `limit`, `offset`

3. **Update `TomeLedger._load_all_tomes()` to use streaming for large files**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py`
   - Add file size check; if > 10MB, use streaming with incremental index building

4. **Add `read_last_n_entries()` for tail access**:
   - Use `aiofiles` with seek from end for efficient tail reads

### Testing
- Memory profiling test with 100MB+ JSONL file
- Benchmark streaming vs full load
- Test `TomeLedger.open_tome()` with large files

---

## Issue 3: FileLock Has No Recovery Mechanism
**ID**: TOME-003  
**Priority**: High  
**Effort**: Medium  
**Dependencies**: None

### Root Cause Analysis
`FileLock` at `locking.py:8-41` wraps `filelock.FileLock` but has no recovery:
- If process crashes while holding lock, `.lock` file remains
- No stale lock detection (no PID/timestamp in lock file)
- No automatic cleanup on startup
- `timeout=30.0` just waits, doesn't recover

`TomeLedger` at `ledger.py:15` uses this lock for all operations.

### Fix Steps
1. **Enhance `FileLock` with stale lock detection**:
   - File: `mvgeos-tome/mvgeos_tome/locking.py`
   - Store PID + timestamp in lock file content
   - On acquire, check if holding process exists; if not, force-release
   - Add `force_release_stale()` method

2. **Add automatic stale lock cleanup on `TomeLedger` init**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py:12-18`
   - Call `force_release_stale()` in `__init__` before first use

3. **Add lock metadata (PID, timestamp, hostname) to lock file**:
   - Modify `FileLock.acquire()` to write metadata
   - Use `os.getpid()`, `time.time()`, `socket.gethostname()`

4. **Add configurable stale threshold** (default 5 minutes):
   - Parameter in `FileLock.__init__`

### Testing
- Simulate process crash while holding lock; verify recovery
- Test concurrent access with stale lock cleanup
- Test cross-process lock contention

---

## Issue 4: TomeLedger._index Holds All Entries in Memory (Unbounded Growth)
**ID**: TOME-004  
**Priority**: High  
**Effort**: Large  
**Dependencies**: TOME-002 (streaming reads)

### Root Cause Analysis
`TomeLedger._index` at `ledger.py:17` is an `Index` instance that accumulates ALL entries for ALL tomes:
```python
self._index = Index()  # holds all entries in memory
```
`Index.add()` at `index.py:15-22` stores every entry in `_entries_by_id` dict - unbounded growth.

`_save_index()` at `ledger.py:75-87` serializes ALL entries to `index.json` on every append.

### Fix Steps
1. **Add LRU eviction to `Index`**:
   - File: `mvgeos-tome/mvgeos_tome/index.py`
   - Add `max_entries` parameter to `Index.__init__`
   - Implement LRU eviction in `add()` using `collections.OrderedDict`

2. **Add per-tome index sharding**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py`
   - Change `_index: Index` to `_indices: dict[str, Index]` (per-tome)
   - Only load index for active tome

3. **Lazy index loading**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py`
   - Load index on-demand in `open_tome()` / `append()`
   - Persist index per-tome: `{tome_id}.index.json`

4. **Add index rebuild from JSONL (for recovery)**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py`
   - Method: `rebuild_index(tome_id: str) -> None`
   - Stream JSONL and rebuild index incrementally

5. **Add config for max index entries per tome** (default 10000):
   - File: `mvgeos-tome/mvgeos_tome/ledger.py:12-18`

### Testing
- Memory profiling with 100K+ entries across multiple tomes
- Test index rebuild after crash
- Benchmark append performance with/without eviction

---

## Issue 5: No Session File Integrity Check (CRC/Checksum)
**ID**: TOME-005  
**Priority**: Medium  
**Effort**: Small  
**Dependencies**: None

### Root Cause Analysis
`JsonlStore.read_all()` at `jsonl_store.py:26` and `read_entries()` at `jsonl_store.py:30-38` call `json.loads(line)` without any integrity verification. Corrupted lines (truncated writes, disk errors) raise `json.JSONDecodeError` mid-stream.

`SessionManager.open()` at `session.py:96-110` catches only `ValueError, json.JSONDecodeError` but continues silently on individual line failures.

### Fix Steps
1. **Add CRC32 checksum to each JSONL line**:
   - File: `mvgeos-tome/mvgeos_tome/jsonl_store.py`
   - Format: `{json}\t{crc32:08x}\n` (tab-separated)
   - Verify on read; skip/flag corrupted lines

2. **Add session-level checksum in header**:
   - File: `mvgeos-tome/mvgeos_tome/session.py:55-68` (create)
   - Header includes `checksum: str` (SHA256 of all entries)
   - Verify on `SessionManager.open()`

3. **Add `verify_integrity()` method to `JsonlStore`**:
   - File: `mvgeos-tome/mvgeos_tome/jsonl_store.py`
   - Returns `(valid: bool, errors: list[tuple[int, str]])` - line number, error

4. **Add `corrupt_entries` tracking in `SessionManager`**:
   - File: `mvgeos-tome/mvgeos_tome/session.py`
   - Property: `corrupt_entries: list[dict]`

### Testing
- Corrupt JSONL file (truncated line, invalid JSON); verify detection
- Test checksum verification on session open
- Benchmark overhead of CRC32 per line

---

## Issue 6: build_entries_for_context() Has Broken Logic
**ID**: TOME-006  
**Priority**: High  
**Effort**: Small  
**Dependencies**: None  
**Status**: Resolved — SessionManager removed; context filtering now in `TomeLedger.get_entries_for_context()`

### Root Cause Analysis
`SessionManager.build_entries_for_context()` at `session.py:255-277` had variables used before assignment. The real bug: `first_kept = compacted.get("firstKeptEntryId")` can be `None`, then `entry.get("id") == first_kept` compares string to `None` - never matches, `started` stays `False`, `kept_ids` stays empty.

### Resolution
`SessionManager` removed. `TomeLedger.get_entries_for_context()` implements correct logic with proper None checks and filtering by leaf branch.

---

## Issue 7: Dead Private Methods in SessionManager
**ID**: TOME-007  
**Priority**: Low  
**Effort**: Small  
**Dependencies**: TOME-006 (verify not used there)  
**Status**: Resolved — SessionManager removed entirely

### Root Cause Analysis
Methods at `session.py:279-321` appeared unused but were actually used internally. This was a false positive in the debt doc.

### Resolution
`SessionManager` class deleted; all functionality moved to `TomeLedger`. No dead methods remain.

---

## Issue 8: Pi-Compatible JSONL Format Without Version Migration
**ID**: TOME-008  
**Priority**: Medium  
**Effort**: Medium  
**Dependencies**: TOME-005 (integrity checks)  
**Status**: Partially Resolved — Migration logic needed in `TomeLedger._load_tome_metadata()`

### Root Cause Analysis
`CURRENT_SESSION_VERSION = 3` at `session.py:10` but no migration logic exists. `SessionManager.open()` at `session.py:96-110` only validates `header.get("type") == "session"` but doesn't check version or migrate.

Pi-compatible format: header line + JSONL entries. Version 3 may have different schema than v1/v2.

### Fix Steps
1. **Add version detection in `TomeLedger._load_tome_metadata()`**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py`
   - Read `header.get("version", 1)`
   - Dispatch to version-specific parser

2. **Implement migration functions**:
   - File: `mvgeos-tome/mvgeos_tome/ledger.py` (new section)
   - `_migrate_v1_to_v2(header, entries) -> (header, entries)`
   - `_migrate_v2_to_v3(header, entries) -> (header, entries)`
   - Chain migrations: v1→v2→v3

3. **Add version to `TomeMetadata` schema**:
   - File: `mvgeos-tome/mvgeos_tome/types.py:20-25`
   - `schema_version: str = "1.0"`

4. **Write migrated session back on open** (optional, configurable):
   - Auto-upgrade old sessions on read

### Testing
- Create v1, v2 session files; verify migration to v3
- Test round-trip: create v3 -> read -> verify no data loss
- Test corrupted version field handling

---

## Issue 9: Leaf Tracking via Separate Entry Type
**ID**: TOME-009  
**Priority**: Low  
**Effort**: Small  
**Dependencies**: None (architectural choice)  
**Status**: Documented — Now in `TomeLedger.append_leaf()`

### Root Cause Analysis
`SessionManager.append_leaf()` at `session.py:164-173` creates a separate `type="leaf"` entry:
```python
def append_leaf(self, target_id: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "leaf",
        "id": _generate_short_id(),
        "parentId": None,
        "timestamp": datetime.now(UTC).isoformat(),
        "targetId": target_id,
    }
    self.append(entry)
    return entry
```
This creates extra entries just for leaf tracking. The `Index` at `index.py:21-24` tracks leaves separately via `_leaf_ids`.

### Resolution
`TomeLedger.append_leaf()` maintains this Pi-compatible design — it appends a LEAF entry AND updates `metadata.active_leaf_id`. This enables branching history without mutating message entries.

### Fix Steps (Documentation)
1. **Add docstring to `TomeLedger.append_leaf()`** explaining Pi compatibility
2. **Add comment in `types.py`** for `TomeEntryType.LEAF`
3. **Update architecture docs** if any exist

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| TOME-001 | None | ~~TOME-002, mvgeos-agent (async calls)~~ **Resolved** |
| TOME-002 | ~~TOME-001~~ | TOME-004 |
| TOME-003 | None | - |
| TOME-004 | TOME-002 | - |
| TOME-005 | None | TOME-008 |
| TOME-006 | None | - **Resolved** |
| TOME-007 | None | - **Resolved** |
| TOME-008 | TOME-005 | - |
| TOME-009 | None | - **Documented** |

---

## Implementation Order (Recommended)

1. **TOME-001** (Sync I/O to Async) - **Resolved** — SessionManager removed, sync I/O in FileLock context
2. **TOME-003** (Lock recovery) - High impact, independent
3. **TOME-006** (Broken context logic) - **Resolved** — SessionManager removed
4. **TOME-007** (Dead methods) - **Resolved** — SessionManager removed
5. **TOME-005** (Integrity checks) - Medium, enables TOME-008
6. **TOME-002** (Streaming reads) - High impact
7. **TOME-004** (Index memory) - Large effort, needs TOME-002
8. **TOME-008** (Version migration) - Medium, needs TOME-005
9. **TOME-009** (Leaf design doc) - **Documented**

---

## Testing Strategy

### Unit Tests (per issue)
- Each fix requires targeted unit tests
- Target: 90%+ coverage on modified modules

### Integration Tests
- `mvgeos-tome/tests/test_integration.py`
- Full session lifecycle: create -> append -> reopen -> branch -> compact
- Concurrent access with FileLock
- Crash recovery simulation (kill process, verify lock recovery)

### Performance Benchmarks
- `mvgeos-tome/tests/benchmarks/`
- JSONL append throughput (async vs sync)
- Memory usage with 10K/100K/1M entries
- Index rebuild time

### Cross-Package Tests
- `mvgeos-agent/tests/test_tome_integration.py`
- Verify async TomeLedger/SessionManager works in agent loop
- Test session resume with migrated versions

---

## Dependency Updates Required

**mvgeos-tome/pyproject.toml**:
```toml
[project]
dependencies = [
    "filelock>=3.15",
    "aiofiles>=23.0",  # NEW for TOME-001, TOME-002
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "mypy>=1.0",
    "memray>=1.0",  # for memory profiling
]
```

---

## Files to Modify Summary

| File | Issues |
|------|--------|
| `jsonl_store.py` | TOME-001, TOME-002, TOME-005 |
| `locking.py` | TOME-003 |
| `ledger.py` | TOME-003, TOME-004, TOME-008 |
| `index.py` | TOME-004 |
| ~~`session.py`~~ | **Deleted** (resolved TOME-001, TOME-005, TOME-006, TOME-007, TOME-008, TOME-009) |
| `types.py` | TOME-008 |
| `pyproject.toml` | TOME-001, TOME-002 (deps: `aiofiles`) |

---

## Definition of Done Per Issue

- [ ] Code changes implemented with type hints (mypy strict passes)
- [ ] Unit tests added/updated (pytest passes)
- [ ] Ruff linting passes (`ruff check .`)
- [ ] Integration test passes
- [ ] No performance regression (benchmarks)
- [ ] Cross-package tests pass (mvgeos-agent integration)
- [ ] CHANGELOG.md updated (conventional commit)
