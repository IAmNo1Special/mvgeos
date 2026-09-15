# mvgeos-Tome — Agent Instructions

This package implements Tome persistence: JSONL session storage with kernel leases and disk-authoritative reads. A Tome is a tree of conversation entries stored in a single Pi-compatible JSONL file.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run python -m pytest mvgeos-tome/tests

# Run with coverage
uv run python -m pytest mvgeos-tome/tests --cov
```

Test paths follow pattern: `mvgeos-tome/tests/unit/<module>.py` and `mvgeos-tome/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `TomeHandleFactory` | Stateless entry point: create/open/fork tomes; disk-authoritative queries; no caches |
| `TomeHandle` | Single-tome handle (read/write); stat-validated in-memory mirror; kernel lease on write |
| `Revision` | Filesystem invalidation token (mtime_ns, size, ino) |
| `TomeStore` | Canonical handle identity per process (no persistence state) |
| `TomeEntry` | Single entry in a Tome (id, parent_id, type, timestamp, payload) |
| `TomeEntryType` | Enum of entry types (MESSAGE, LABEL, COMPACTION, CUSTOM, LEAF, TOME_INFO) |
| `TomeMetadata` | Tome header (id, created_at, cwd, parent_tome_id, active_leaf_id) |

## TomeEntryType Values

| Value | Purpose |
| --- | --- |
| `MESSAGE` | User, assistant, and tool messages |
| `LABEL` | Label/tag on an entry |
| `COMPACTION` | Context compaction summary |
| `CUSTOM` | Arbitrary extension/sigil data |
| `LEAF` | Active position marker (current tip of a conversation branch) |
| `TOME_INFO` | Tome metadata (name, etc.) |

## Entry Type Naming

- `TOME_INFO` (not `SESSION_INFO`) — aligns with MvgeOS "Tome" terminology

## Dependencies

- `portalocker` — kernel lease locking (flock / Windows mutex)

## Architecture

- One `{tome_id}.jsonl` per Tome in a tome directory
- Line 1 = header `{"type":"session","version":1,"id","timestamp","cwd","parentSession"?,"activeLeafId"?}`
- Subsequent lines = entries `{"id","parentId","type","timestamp","payload"}`
- Appends are single-line writes with fsync; only compaction/fork rewrites the file (tmp + atomic rename)
- Every read revalidates against the filesystem revision; the JSONL file is the source of truth
- Writes hold a kernel lease; torn tails are truncated by the resumer via `repair_torn_tail`
- Forking creates a new Tome by copying the ancestor chain up to a chosen entry
